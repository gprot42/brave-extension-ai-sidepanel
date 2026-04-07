# A simple type validator to check types of bencoded data that comes from
# an untrusted source (say, network).
#
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSE for more information.
#
# Originally written by Heikki Orsila <heikki.orsila@iki.fi> on 2009-09-12
#
# Repository at https://gitlab.com/heikkiorsila/bencodetools

from types import FunctionType

# BOOL*, INT*, STRING* and FLOAT* are used for backward compability
# with the old interface. New code should use bool/int/str/float directly.
BOOL = bool
BOOL_KEY = bool
INT = int
INT_KEY = int
STRING = str
STRING_KEY = str
FLOAT = float
FLOAT_KEY = float

# ANY is used for backwards compatibility. Use object in new code instead.
ANY = object


class ZERO_OR_MORE:
    pass


class ONE_OR_MORE:
    pass


class OPTIONAL_KEY:
    def __init__(self, key):
        if type(key) == type:
            raise ValueError('key {} must not be a type'.format(key))
        self.key = key


class ValidationError(ValueError):
    def __init__(self, reason='', fmt=None, obj=None):
        self._reason = reason
        self.fmt = fmt
        self.obj = obj

    def __str__(self):
        return self._reason


# Define Invalid_Format_Object for backwards compatibility
Invalid_Format_Object = ValidationError


class Context:
    def __init__(self, raise_error=False):
        self._stack = []
        self._raise_error = raise_error

    def error(self, fmt, obj):
        if self._raise_error:
            raise ValidationError(
                reason=('Validation error: {} expected format is '
                        '{} and value is {}'.format(
                            self._print_stack(), repr(fmt), repr(obj))),
                fmt=fmt, obj=obj)

    def error2(self, msg, fmt, obj):
        if self._raise_error:
            raise ValidationError(
                reason=('Validation error: {} {}'.format(
                    self._print_stack(), msg)),
                fmt=fmt, obj=obj)

    def _print_stack(self):
        if len(self._stack) == 0:
            return 'At root position'
        return 'At position ' + ''.join(self._stack)

    def pop(self):
        self._stack.pop()

    def push(self, s):
        self._stack.append(s)

    def is_root(self):
        return len(self._stack) == 0


# Example:
#
# SPEC = {'value': one_of(['x', 'y'])}
#
# then validate(SPEC, d) means that d['value'] must be either 'x' or 'y'
def one_of(alternatives):
    d = {}
    for alternative in alternatives:
        d[alternative] = alternative

    def test_f(o):
        return o in d and isinstance(o, type(d[o]))

    return test_f


# Example:
#
# SPEC = {'value': union_type([int, float])}
#
# then validate(SPEC, d) means that d['value'] must be either a float or
# an int.
def union_type(alternative_types):
    valid_types = set(alternative_types)

    def test_f(o):
        return type(o) in valid_types

    return test_f


def _validate_list(org_fmt, org_o, ctx):
    if isinstance(org_fmt, list):
        fmt_type = list
        fmt_type_str = 'list'
    else:
        fmt_type = tuple
        fmt_type_str = 'tuple'

    if type(org_o) != fmt_type:
        ctx.error2('expect a {}. Class is {}'.format(
            fmt_type_str, type(org_o)), fmt_type, org_o)
        return False

    if ctx.is_root():
        ctx.push('[]')

    fmt = list(org_fmt)
    o = list(org_o)
    pos = 0
    while len(fmt) > 0:
        fitem = fmt.pop(0)
        if fitem == ZERO_OR_MORE or fitem == ONE_OR_MORE:
            if len(fmt) == 0:
                raise ValidationError(
                    'In {} fmt {}: missing list element type'.format(
                        fmt_type_str, org_fmt))
            ftype = fmt.pop(0)
            if len(o) == 0:
                if fitem == ONE_OR_MORE:
                    ctx.error2('expect a value in {}, '
                               'but there is none.'.format(fmt_type_str),
                               fmt=org_fmt, obj=org_o)
                    return False
                continue

            while len(o) > 0:
                ctx.push('[{}]'.format(pos))
                if not _validate(ftype, o[0], ctx):
                    # This is somewhat esoteric. It is possible to concatenate
                    # list segments of different types.
                    # E.g. [ONE_OR_MORE, int, ZERO_OR_MORE, str].
                    if len(fmt) > 0:
                        break
                    return False
                ctx.pop()
                o.pop(0)
                pos += 1
            continue

        if len(o) == 0:
            ctx.error2('expect a value in {}, but there is none.'.format(
                fmt_type_str), fmt=org_fmt, obj=org_o)
            return False
        oitem = o.pop(0)
        ctx.push('[{}]'.format(pos))
        if not _validate(fitem, oitem, ctx):
            return False
        ctx.pop()
        pos += 1

    ret = (len(o) == 0)
    if not ret:
        ctx.error(org_fmt, org_o)

    if ctx.is_root():
        ctx.pop('[]')

    return ret


def _validate_dict(fmt, o, ctx):
    if type(o) != dict:
        ctx.error2('expect a dict. Class is {}'.format(type(o)), dict, o)
        return False

    if ctx.is_root():
        ctx.push('{}')

    for key in fmt:
        key_type = type(key)
        if isinstance(key, OPTIONAL_KEY):
            # OPTIONAL_KEY
            if key.key in o:
                ctx.push('[{}]'.format(repr(key.key)))
                if not _validate(fmt[key], o[key.key], ctx):
                    return False
                ctx.pop()
        elif key_type == type:
            # str, int, ...
            for okey in o:
                if key is not object:
                    if type(okey) == type or type(okey) != key:
                        ctx.error2(
                            'expect key in {} but key is {}'.format(
                                key, repr(okey)), key, okey)
                        return False
                ctx.push('[{}]'.format(repr(okey)))
                if not _validate(fmt[key], o[okey], ctx):
                    return False
                ctx.pop()
        elif key_type == FunctionType:
            for okey in o:
                ctx.push('[key:{}]'.format(repr(okey)))
                if not _validate(key, okey, ctx):
                    return False
                ctx.pop()
                ctx.push('[{}]'.format(repr(okey)))
                if not _validate(fmt[key], o[okey], ctx):
                    return False
                ctx.pop()
        else:
            # Key is a value, not a type. It must exist in the object.
            if key not in o:
                ctx.error2('key {} does not exist'.format(repr(key)), fmt, o)
                return False
            ctx.push('[{}]'.format(repr(key)))
            if not _validate(fmt[key], o[key], ctx):
                return False
            ctx.pop()

    if ctx.is_root():
        ctx.pop()

    return True


def _validate_set(fmt, o, ctx):
    if type(o) != set:
        ctx.error2('expect a set. Class is {}'.format(type(o)), set, o)
        return False

    if ctx.is_root():
        ctx.push('set()')

    for value in fmt:
        value_type = type(value)
        if value == ZERO_OR_MORE:
            pass
        elif value == ONE_OR_MORE:
            if len(o) == 0:
                ctx.error2('Expected at least one element in the list',
                           value, o)
                return False
        elif value_type == type:
            # str, int, ...
            for ovalue in o:
                if value is not object:
                    if type(ovalue) == type or type(ovalue) != value:
                        ctx.error2(
                            'expect value in {} but value is {}'.format(
                                value, repr(ovalue)), value, ovalue)
                        return False
        elif value_type == FunctionType:
            for ovalue in o:
                ctx.push('[value:{}]'.format(repr(ovalue)))
                if not _validate(value, ovalue, ctx):
                    return False
                ctx.pop()
        else:
            # Value is not a type. It must exist in the set.
            if value not in o:
                ctx.error2('value {} does not exist'.format(repr(value)),
                           fmt, o)
                return False

    if ctx.is_root():
        ctx.pop()

    return True


def _validate_function_type(fmt, o, ctx):
    # fmt is a user given checker function
    ret = fmt(o)
    if not ret:
        ctx.error2('function call {}({}) returns False'.format(
            fmt.__name__, repr(o)), fmt, o)
    return ret


def _validate_type(fmt, o, ctx):
    if type(o) != fmt and fmt is not object:
        ctx.error2('expect type {} and value is {}'.format(
            fmt.__name__, repr(o)), fmt, o)
        return False
    return True


TYPE_HANDLERS = {
    FunctionType: _validate_function_type,
    list: _validate_list,
    dict: _validate_dict,
    set: _validate_set,
    tuple: _validate_list,
    type: _validate_type,
}


def _validate(fmt, o, ctx):
    validator = TYPE_HANDLERS.get(type(fmt))
    if validator is not None:
        return validator(fmt, o, ctx)

    # If given format is a not a type but a value, compare input to the
    # given value
    ret = (fmt == o)
    if not ret:
        ctx.error2('expect value {}, but value is {}'.format(
            repr(fmt), repr(o)), fmt, o)
    return ret


def validate(fmt, o):
    """Returns True if o is valid with respect to fmt, False otherwise."""
    ctx = Context()
    return _validate(fmt, o, ctx)


def validate2(fmt, o):
    """Similar to validate() but raises ValidationError() if o is not valid.

    ValidationError is a subclass of ValueError.
    Catching ValidationError rather than ValueError allows to gain insight
    where the validation failed inside o.

    Returns the object o after validation.
    """
    ctx = Context(raise_error=True)
    _validate(fmt, o, ctx)
    return o


def test_validate():
    # Test list validation
    assert validate(
        [str, [ONE_OR_MORE, int], [ZERO_OR_MORE, int], {'a': int, 1: str}],
        ['fff', [0], [], {'a': 0, 1: 'foo'}])
    assert not validate(
        [str, [ONE_OR_MORE, int], [ZERO_OR_MORE, int], {'a': int, 1: str}],
        [1, [0], [], {'a': 0, 1: 'foo'}])
    assert not validate(
        [str, [ONE_OR_MORE, int], [ZERO_OR_MORE, int], {'a': int, 1: str}],
        ['fff', [], [], {'a': 0, 1: 'foo'}])
    assert validate([ONE_OR_MORE, int, ZERO_OR_MORE, str], [1, 1, 1])
    assert validate([ONE_OR_MORE, int, ZERO_OR_MORE, str], [1, 1, 1, 's'])
    assert validate([ZERO_OR_MORE, int, ONE_OR_MORE, str], [1, 1, 1, 's'])
    assert not validate([ZERO_OR_MORE, int, ONE_OR_MORE, str], [1, 1, 1])
    assert validate([ZERO_OR_MORE, int, ONE_OR_MORE, str], ['d'])
    assert not validate([ZERO_OR_MORE, int, ONE_OR_MORE, str], [])

    # Test tuple validation
    assert validate(
        (str, [ONE_OR_MORE, int], [ZERO_OR_MORE, int], {'a': int, 1: str}),
        ('fff', [0], [], {'a': 0, 1: 'foo'}))
    assert not validate(
        (str, [ONE_OR_MORE, int], [ZERO_OR_MORE, int], {'a': int, 1: str}),
        (1, [0], [], {'a': 0, 1: 'foo'}))
    assert not validate(
        (str, [ONE_OR_MORE, int], [ZERO_OR_MORE, int], {'a': int, 1: str}),
        ('fff', [], [], {'a': 0, 1: 'foo'}))
    assert validate((ONE_OR_MORE, int, ZERO_OR_MORE, str), (1, 1, 1))
    assert validate((ONE_OR_MORE, int, ZERO_OR_MORE, str), (1, 1, 1, 's'))
    assert validate((ZERO_OR_MORE, int, ONE_OR_MORE, str), (1, 1, 1, 's'))
    assert not validate((ZERO_OR_MORE, int, ONE_OR_MORE, str), (1, 1, 1))
    assert validate((ZERO_OR_MORE, int, ONE_OR_MORE, str), ('d', ))
    assert not validate((ZERO_OR_MORE, int, ONE_OR_MORE, str), tuple())
    validate2((union_type([int, float]), union_type([int, float])),
              (1, 2))
    assert not validate((ONE_OR_MORE, union_type([int, float])), tuple())
    assert validate((ONE_OR_MORE, union_type([int, float])), (1, ))

    assert not validate((int, ), [int, ])
    assert not validate([int, ], (tuple, ))

    assert validate((int, ), (1, ))
    assert not validate((int, ), (1, 2))
    assert not validate((int, str), (1, ))
    assert validate((int, str), (1, 'a'))

    assert validate(lambda x: x % 2 == 0, 0)
    assert not validate(lambda x: x % 2 == 0, 1)

    assert validate({str: str}, {'a': 'b'})
    assert not validate({str: str}, {1: 'b'})
    assert not validate({str: str}, {'a': 1})
    assert validate({str: int}, {'a': 1})
    assert validate({int: str}, {1: 'a'})
    assert not validate({int: str}, {1: 'a', 'b': 2})

    # Extra keys in dictionary are allowed
    assert validate({'x': int}, {'x': 1, 'y': 1})
    # Missing key fails
    assert not validate({'x': int}, {'y': 1})

    # OK
    assert validate({'x': int, str: int}, {'x': 1, 'y': 1})
    # Non-string key
    assert not validate({'x': int, str: int}, {'x': 1, 1: 1})
    # Missing key, but correct key type
    assert not validate({'x': int, str: int}, {'y': 1})

    assert validate({'x': bool}, {'x': False})
    assert not validate({'x': bool}, {'x': 0})

    # Test OPTIONAL_KEY
    assert validate({OPTIONAL_KEY('x'): int}, {})
    assert validate({OPTIONAL_KEY('x'): int}, {'x': 1})
    assert not validate({OPTIONAL_KEY('x'): int}, {'x': 'invalid'})

    # Typevalidator can be used to check that values are equal
    assert validate([1, 2, 3, [True, 'a']], [1, 2, 3, [True, 'a']])
    assert not validate('foo', 'bar')

    assert validate(float, 0.0)
    assert not validate(float, 1)

    assert validate({'value': one_of(['x', 'y'])}, {'value': 'x'})
    assert not validate({'value': one_of(['x', 'y'])}, {'value': 'z'})

    # Test ANY as dict key
    assert validate({ANY: int}, {'1': 1, 2: 2})
    assert validate({ANY: int}, {str: 1})
    assert validate({str: ANY}, {'1': ANY})
    assert validate({ANY: ANY}, {ANY: ANY})

    # Test ANY as list type
    assert validate([ZERO_OR_MORE, ANY], [])
    assert validate([ZERO_OR_MORE, ANY], [1])
    assert validate([ZERO_OR_MORE, ANY], [1, '2'])
    assert validate([ZERO_OR_MORE, ANY], [1, '2', ANY])

    assert not validate({str: int}, {str: 1})
    assert not validate({str: int}, {'x': int})

    try:
        validate({OPTIONAL_KEY(str): str}, {'1': '2'})
        assert False
    except ValueError:
        pass

    # Test validation exceptions
    assert validate2(int, 1) == 1

    try:
        validate2(int, '1')
        assert False
    except ValueError:
        pass
    try:
        validate2([ZERO_OR_MORE, int], ['x'])
        assert False
    except ValueError:
        pass
    try:
        validate2(['x'], [1])
        assert False
    except ValueError:
        pass
    try:
        validate2(['x'], 's')
        assert False
    except ValueError:
        pass
    try:
        validate2({'x': int}, {'x': 'y'})
        assert False
    except ValueError:
        pass
    try:
        validate2({str: int}, {1: 'y'})
        assert False
    except ValueError:
        pass
    try:
        validate2([], 'x')
        assert False
    except ValueError:
        pass
    try:
        validate2(['x'], [])
        assert False
    except ValueError:
        pass
    try:
        validate2({}, [])
        assert False
    except ValueError:
        pass
    try:
        validate2({'x': int}, {})
        assert False
    except ValueError:
        pass
    try:
        validate2(lambda x: (x & 1) == 0, 1)
        assert False
    except ValueError:
        pass

    try:
        validate2({'x': [ZERO_OR_MORE, str]}, {'x': ['y', 0]})
        assert False
    except ValueError:
        pass
    assert validate({'x': [ZERO_OR_MORE, {'y': dict}]}, {'x': []})
    assert validate({'x': [ZERO_OR_MORE, {'y': dict}]}, {'x': [{'y': {}}]})

    assert not validate({'x': [ONE_OR_MORE, {'y': dict}]}, {'x': []})

    assert validate(union_type([int, float]), 1)
    assert validate(union_type([int, float]), 2.0)
    assert not validate(union_type([int, float]), '3')

    assert validate(ANY, 0)
    assert validate(object, 0)
    assert validate(ANY, False)
    assert validate(object, False)

    # Test list function validator
    assert validate([ZERO_OR_MORE,
                     lambda x: type(x) == int and (x % 2) == 0], [2])
    assert not validate([ZERO_OR_MORE,
                         lambda x: type(x) == int and (x % 2) == 0], [2, 3])
    assert not validate([ZERO_OR_MORE,
                         lambda x: type(x) == int and (x % 2) == 0], ['2'])

    # Test dict key function validator
    assert validate({lambda x: isinstance(x, int) and (x % 2) == 0: str},
                    {2: 'a'})
    assert not validate({lambda x: isinstance(x, int) and (x % 2) == 0: str},
                        {3: 'a'})
    assert not validate({lambda x: isinstance(x, int) and (x % 2) == 0: str},
                        {2: 1})

    # Test set validation
    assert validate({str}, {'a', })
    assert not validate({str}, {1, })
    assert not validate({str}, {1, 'a'})
    assert not validate({str}, {'a', 1})

    assert validate({ZERO_OR_MORE}, set())
    assert validate({ZERO_OR_MORE}, {'a', })
    assert not validate({ONE_OR_MORE}, set())
    try:
        validate2({ONE_OR_MORE}, set())
        assert False
    except ValueError:
        pass
    assert validate({ONE_OR_MORE}, {'a', })
    assert validate(set, set())
    assert validate({ONE_OR_MORE, str}, {'a', })
    assert not validate({ONE_OR_MORE, str}, set())
    assert not validate({ONE_OR_MORE, str}, {1, })
    assert validate({ZERO_OR_MORE, str}, set())

    assert validate({lambda x: isinstance(x, int) and (x % 2) == 0}, {2, })
    assert not validate({lambda x: isinstance(x, int) and (x % 2) == 0}, {3, })

    assert validate({str, 'x'}, {'x'})
    assert validate({str, 'x'}, {'x', 'y'})
    assert not validate({str, 'x'}, {'y'})

    assert validate({str, one_of(['x', 'y'])}, {'y'})
    assert validate({str, one_of(['x', 'y'])}, {'x', 'y'})
    assert not validate({str, one_of(['x', 'y'])}, {'x', 'z'})


if __name__ == '__main__':
    test_validate()
