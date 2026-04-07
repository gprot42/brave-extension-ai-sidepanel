/**
 * Joplin Commands API interface
 * Allows registering and executing commands
 */

export interface Command {
  name: string;
  label: string;
  iconName?: string;
  execute: (...args: unknown[]) => Promise<unknown>;
}

declare class JoplinCommands {
  /**
   * Registers a new command
   */
  register(command: Command): Promise<void>;

  /**
   * Executes a command by name
   */
  execute(commandName: string, ...args: unknown[]): Promise<unknown>;
}

export default JoplinCommands;