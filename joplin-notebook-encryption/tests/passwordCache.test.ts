/**
 * Password Cache Tests
 */

import { PasswordCache } from '../src/services/passwordCache';

describe('PasswordCache', () => {
  let cache: PasswordCache;

  beforeEach(() => {
    cache = new PasswordCache(1); // 1 minute timeout for testing
    jest.useFakeTimers();
  });

  afterEach(() => {
    cache.clearAll();
    jest.useRealTimers();
  });

  describe('set and get', () => {
    it('should store and retrieve a password', () => {
      cache.set('notebook-1', 'password123');
      expect(cache.get('notebook-1')).toBe('password123');
    });

    it('should return null for non-existent notebook', () => {
      expect(cache.get('non-existent')).toBeNull();
    });

    it('should overwrite existing password', () => {
      cache.set('notebook-1', 'password123');
      cache.set('notebook-1', 'newpassword');
      expect(cache.get('notebook-1')).toBe('newpassword');
    });

    it('should store passwords for multiple notebooks', () => {
      cache.set('notebook-1', 'password1');
      cache.set('notebook-2', 'password2');
      cache.set('notebook-3', 'password3');
      
      expect(cache.get('notebook-1')).toBe('password1');
      expect(cache.get('notebook-2')).toBe('password2');
      expect(cache.get('notebook-3')).toBe('password3');
    });
  });

  describe('has', () => {
    it('should return true for cached password', () => {
      cache.set('notebook-1', 'password123');
      expect(cache.has('notebook-1')).toBe(true);
    });

    it('should return false for non-existent password', () => {
      expect(cache.has('non-existent')).toBe(false);
    });
  });

  describe('clear', () => {
    it('should remove a specific cached password', () => {
      cache.set('notebook-1', 'password1');
      cache.set('notebook-2', 'password2');
      
      cache.clear('notebook-1');
      
      expect(cache.get('notebook-1')).toBeNull();
      expect(cache.get('notebook-2')).toBe('password2');
    });

    it('should handle clearing non-existent entry', () => {
      expect(() => cache.clear('non-existent')).not.toThrow();
    });
  });

  describe('clearAll', () => {
    it('should remove all cached passwords', () => {
      cache.set('notebook-1', 'password1');
      cache.set('notebook-2', 'password2');
      cache.set('notebook-3', 'password3');
      
      cache.clearAll();
      
      expect(cache.get('notebook-1')).toBeNull();
      expect(cache.get('notebook-2')).toBeNull();
      expect(cache.get('notebook-3')).toBeNull();
    });
  });

  describe('expiration', () => {
    it('should expire password after timeout', () => {
      cache.set('notebook-1', 'password123');
      
      // Fast-forward time past expiry
      jest.advanceTimersByTime(61 * 1000); // 61 seconds
      
      expect(cache.get('notebook-1')).toBeNull();
    });

    it('should not expire password before timeout', () => {
      cache.set('notebook-1', 'password123');
      
      // Fast-forward but not past expiry
      jest.advanceTimersByTime(30 * 1000); // 30 seconds
      
      expect(cache.get('notebook-1')).toBe('password123');
    });
  });

  describe('refresh', () => {
    it('should reset expiry time', () => {
      cache.set('notebook-1', 'password123');
      
      // Wait 45 seconds
      jest.advanceTimersByTime(45 * 1000);
      
      // Refresh the cache
      cache.refresh('notebook-1');
      
      // Wait another 45 seconds (would have expired without refresh)
      jest.advanceTimersByTime(45 * 1000);
      
      // Should still be valid
      expect(cache.get('notebook-1')).toBe('password123');
    });
  });

  describe('setTimeout', () => {
    it('should update timeout for new entries', () => {
      cache.setTimeout(2); // 2 minutes
      cache.set('notebook-1', 'password123');
      
      // Wait 1.5 minutes
      jest.advanceTimersByTime(90 * 1000);
      
      // Should still be valid
      expect(cache.get('notebook-1')).toBe('password123');
      
      // Wait another minute
      jest.advanceTimersByTime(60 * 1000);
      
      // Should be expired now
      expect(cache.get('notebook-1')).toBeNull();
    });
  });

  describe('getTimeout', () => {
    it('should return current timeout in minutes', () => {
      expect(cache.getTimeout()).toBe(1);
      
      cache.setTimeout(5);
      expect(cache.getTimeout()).toBe(5);
    });
  });

  describe('getRemainingTime', () => {
    it('should return remaining time until expiry', () => {
      cache.set('notebook-1', 'password123');
      
      // Initial time should be close to full timeout
      const initialRemaining = cache.getRemainingTime('notebook-1');
      expect(initialRemaining).toBeGreaterThan(59 * 1000);
      expect(initialRemaining).toBeLessThanOrEqual(60 * 1000);
      
      // After 30 seconds
      jest.advanceTimersByTime(30 * 1000);
      const laterRemaining = cache.getRemainingTime('notebook-1');
      expect(laterRemaining).toBeGreaterThan(29 * 1000);
      expect(laterRemaining).toBeLessThanOrEqual(30 * 1000);
    });

    it('should return 0 for non-existent entry', () => {
      expect(cache.getRemainingTime('non-existent')).toBe(0);
    });
  });

  describe('getCachedNotebookIds', () => {
    it('should return all cached notebook IDs', () => {
      cache.set('notebook-1', 'password1');
      cache.set('notebook-2', 'password2');
      cache.set('notebook-3', 'password3');
      
      const ids = cache.getCachedNotebookIds();
      expect(ids).toHaveLength(3);
      expect(ids).toContain('notebook-1');
      expect(ids).toContain('notebook-2');
      expect(ids).toContain('notebook-3');
    });

    it('should not include expired entries', () => {
      cache.set('notebook-1', 'password1');
      cache.set('notebook-2', 'password2');
      
      // Expire notebook-1 by clearing and re-adding with expired time
      jest.advanceTimersByTime(61 * 1000);
      
      // Re-add notebook-2
      cache.set('notebook-2', 'password2');
      
      const ids = cache.getCachedNotebookIds();
      expect(ids).toHaveLength(1);
      expect(ids).toContain('notebook-2');
    });
  });
});