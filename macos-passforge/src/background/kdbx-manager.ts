import * as kdbxweb from 'kdbxweb';
import type { KdbxEntryData } from '../shared/types';
import { extractDomain, domainMatches } from '../shared/crypto-utils';

let currentDb: kdbxweb.Kdbx | null = null;

export async function importDatabase(data: ArrayBuffer, keyFileData?: ArrayBuffer): Promise<void> {
  const dataArray = Array.from(new Uint8Array(data));
  const storage: Record<string, unknown> = { kdbxData: dataArray };

  if (keyFileData) {
    storage.keyFileData = Array.from(new Uint8Array(keyFileData));
  }

  await chrome.storage.local.set(storage);
}

export async function removeDatabase(): Promise<void> {
  lockDatabase();
  await chrome.storage.local.remove(['kdbxData', 'keyFileData']);
}

export async function hasDatabase(): Promise<boolean> {
  const result = await chrome.storage.local.get('kdbxData');
  return !!result.kdbxData;
}

export async function unlockDatabase(password: string, keyFileData?: ArrayBuffer): Promise<number> {
  const result = await chrome.storage.local.get(['kdbxData', 'keyFileData']);
  if (!result.kdbxData) {
    throw new Error('No database imported');
  }

  const dbData = new Uint8Array(result.kdbxData as number[]).buffer;

  let keyFile: ArrayBuffer | undefined = keyFileData;
  if (!keyFile && result.keyFileData) {
    keyFile = new Uint8Array(result.keyFileData as number[]).buffer;
  }

  const credentials = new kdbxweb.Credentials(
    kdbxweb.ProtectedValue.fromString(password),
    keyFile ? new Uint8Array(keyFile) : undefined
  );

  currentDb = await kdbxweb.Kdbx.load(dbData, credentials);

  let count = 0;
  for (const _ of currentDb.getDefaultGroup().allEntries()) {
    count++;
  }
  return count;
}

export function lockDatabase(): void {
  if (currentDb) {
    currentDb = null;
  }
}

export function isUnlocked(): boolean {
  return currentDb !== null;
}

export function getEntryCount(): number {
  if (!currentDb) return 0;
  let count = 0;
  for (const _ of currentDb.getDefaultGroup().allEntries()) {
    count++;
  }
  return count;
}

function fieldToString(field: unknown): string {
  if (!field) return '';
  if (typeof field === 'string') return field;
  if (field instanceof kdbxweb.ProtectedValue) return field.getText();
  return String(field);
}

function entryToData(entry: kdbxweb.KdbxEntry, groupName: string): KdbxEntryData {
  return {
    uuid: entry.uuid.toString(),
    title: fieldToString(entry.fields.get('Title')),
    username: fieldToString(entry.fields.get('UserName')),
    password: fieldToString(entry.fields.get('Password')),
    url: fieldToString(entry.fields.get('URL')),
    notes: fieldToString(entry.fields.get('Notes')),
    icon: entry.icon ?? 0,
    groupName,
  };
}

export function searchEntries(query: string, url?: string): KdbxEntryData[] {
  if (!currentDb) return [];

  const results: KdbxEntryData[] = [];
  const lowerQuery = query.toLowerCase();

  function traverseGroup(group: kdbxweb.KdbxGroup) {
    const groupName = group.name ?? '';

    for (const entry of group.entries) {
      if (entry.parentGroup?.uuid.equals(currentDb!.meta.recycleBinUuid ?? kdbxweb.KdbxUuid.random())) {
        continue;
      }

      const data = entryToData(entry, groupName);

      // URL-based matching (no query needed)
      if (url && !query) {
        if (domainMatches(data.url, url)) {
          results.push(data);
        }
        continue;
      }

      // Text search
      if (query) {
        const searchable = [data.title, data.username, data.url, data.notes]
          .join(' ')
          .toLowerCase();
        if (searchable.includes(lowerQuery)) {
          // If URL provided, boost domain matches
          results.push(data);
        }
        continue;
      }

      // No query, no URL - return all
      results.push(data);
    }

    for (const subGroup of group.groups) {
      if (!subGroup.uuid.equals(currentDb!.meta.recycleBinUuid ?? kdbxweb.KdbxUuid.random())) {
        traverseGroup(subGroup);
      }
    }
  }

  traverseGroup(currentDb.getDefaultGroup());

  // Sort: URL matches first if URL provided
  if (url) {
    results.sort((a, b) => {
      const aMatch = domainMatches(a.url, url) ? 0 : 1;
      const bMatch = domainMatches(b.url, url) ? 0 : 1;
      return aMatch - bMatch;
    });
  }

  return results;
}

export function getEntriesForUrl(url: string): KdbxEntryData[] {
  return searchEntries('', url);
}
