export function getManualEvidenceIssue(
  note: string,
  _test?: { testNumber?: string; testName?: string }
): string | null {
  return note.trim() ? null : 'Add engineer notes before saving this manual verdict.'
}
