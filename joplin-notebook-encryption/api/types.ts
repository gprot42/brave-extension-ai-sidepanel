/**
 * Joplin Plugin API Type Definitions
 */

export enum ContentScriptType {
  MarkdownItPlugin = 'markdownItPlugin',
  CodeMirrorPlugin = 'codeMirrorPlugin',
}

export enum SettingItemType {
  Int = 1,
  String = 2,
  Bool = 3,
  Array = 4,
  Object = 5,
  Button = 6,
}

export enum SettingItemSubType {
  FilePathAndArgs = 'file_path_and_args',
  FilePath = 'file_path',
  DirectoryPath = 'directory_path',
}

export enum ToolbarButtonLocation {
  EditorToolbar = 'editorToolbar',
  NoteToolbar = 'noteToolbar',
}

export enum MenuItemLocation {
  File = 'file',
  Edit = 'edit',
  View = 'view',
  Note = 'note',
  Tools = 'tools',
  Help = 'help',
  Context = 'context',
  EditorContextMenu = 'editorContextMenu',
  FolderContextMenu = 'folderContextMenu',
  NoteListContextMenu = 'noteListContextMenu',
  TagContextMenu = 'tagContextMenu',
}

export enum ImportModuleOutputFormat {
  Markdown = 'md',
  Html = 'html',
}

export interface ImportContext {
  sourcePath: string;
  options: Record<string, unknown>;
  warnings: string[];
}

export interface ExportContext {
  destPath: string;
  options: Record<string, unknown>;
}

export interface SettingItem {
  value: unknown;
  type: SettingItemType;
  subType?: SettingItemSubType;
  public: boolean;
  label: string;
  description?: string;
  isEnum?: boolean;
  options?: Record<string, string>;
  section?: string;
  minimum?: number;
  maximum?: number;
  step?: number;
  advanced?: boolean;
  secure?: boolean;
}

export interface SettingSection {
  label: string;
  iconName?: string;
  description?: string;
}

export interface MenuItem {
  commandName?: string;
  accelerator?: string;
  label?: string;
  submenu?: MenuItem[];
}

export interface Note {
  id: string;
  parent_id: string;
  title: string;
  body: string;
  created_time: number;
  updated_time: number;
  is_conflict: number;
  latitude: number;
  longitude: number;
  altitude: number;
  author: string;
  source_url: string;
  is_todo: number;
  todo_due: number;
  todo_completed: number;
  source: string;
  source_application: string;
  application_data: string;
  order: number;
  user_created_time: number;
  user_updated_time: number;
  encryption_cipher_text: string;
  encryption_applied: number;
  markup_language: number;
  is_shared: number;
  share_id: string;
  conflict_original_id: string;
  master_key_id: string;
}

export interface Folder {
  id: string;
  title: string;
  created_time: number;
  updated_time: number;
  user_created_time: number;
  user_updated_time: number;
  encryption_cipher_text: string;
  encryption_applied: number;
  parent_id: string;
  is_shared: number;
  share_id: string;
  master_key_id: string;
  icon: string;
}

export interface Tag {
  id: string;
  title: string;
  created_time: number;
  updated_time: number;
  user_created_time: number;
  user_updated_time: number;
  encryption_cipher_text: string;
  encryption_applied: number;
  is_shared: number;
  parent_id: string;
}

export interface Resource {
  id: string;
  title: string;
  mime: string;
  filename: string;
  created_time: number;
  updated_time: number;
  user_created_time: number;
  user_updated_time: number;
  file_extension: string;
  encryption_cipher_text: string;
  encryption_applied: number;
  encryption_blob_encrypted: number;
  size: number;
  is_shared: number;
  share_id: string;
  master_key_id: string;
}

export interface DialogResult {
  id: string;
  formData?: Record<string, Record<string, string>>;
}

export interface ButtonSpec {
  id: string;
  title?: string;
}