/**
 * Joplin Data API interface
 * Provides access to notes, folders, tags, and resources
 */

export type Path = string[];

export interface GetOptions {
  fields?: string[];
  page?: number;
  limit?: number;
  order_by?: string;
  order_dir?: 'ASC' | 'DESC';
}

export interface PaginatedResults<T> {
  items: T[];
  has_more: boolean;
}

declare class JoplinData {
  /**
   * Gets one or multiple items
   * @param path Path to the resource, e.g., ['notes', noteId]
   * @param query Query parameters
   */
  get(path: Path, query?: GetOptions): Promise<unknown>;

  /**
   * Creates a new item
   * @param path Path to the resource collection, e.g., ['notes']
   * @param query Query parameters
   * @param body Item data
   */
  post(path: Path, query: Record<string, unknown> | null, body: Record<string, unknown>): Promise<unknown>;

  /**
   * Updates an existing item
   * @param path Path to the resource, e.g., ['notes', noteId]
   * @param query Query parameters
   * @param body Updated data
   */
  put(path: Path, query: Record<string, unknown> | null, body: Record<string, unknown>): Promise<unknown>;

  /**
   * Deletes an item
   * @param path Path to the resource, e.g., ['notes', noteId]
   * @param query Query parameters
   */
  delete(path: Path, query?: Record<string, unknown>): Promise<void>;
}

export default JoplinData;