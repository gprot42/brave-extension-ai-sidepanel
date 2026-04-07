from PIL.Image import Image
import unittest
from uade import plot_image


class TestPlogImage(unittest.TestCase):
    def test_test_image(self):
        plot_image.init_colors(0)
        im = plot_image.test_image(640, 2, 4)
        assert isinstance(im, Image)


if __name__ == '__main__':
    unittest.main()
