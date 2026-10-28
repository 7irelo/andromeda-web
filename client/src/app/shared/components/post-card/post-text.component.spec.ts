import { segmentText } from './post-text.component';

describe('segmentText', () => {
  it('links hashtags and mentions and keeps the rest as text', () => {
    expect(segmentText('Run with @thandi at #JoburgRuns!')).toEqual([
      { kind: 'text', text: 'Run with ' },
      { kind: 'mention', text: '@thandi', value: 'thandi' },
      { kind: 'text', text: ' at ' },
      { kind: 'tag', text: '#JoburgRuns', value: 'joburgruns' },
      { kind: 'text', text: '!' },
    ]);
  });

  it('ignores emails, doubled markers and one-letter tags', () => {
    const kinds = segmentText('mail a@b.co, ##ab or #a').map((s) => s.kind);
    expect(kinds).toEqual(['text']);
  });

  it('drops a sentence-ending full stop from a mention', () => {
    const seg = segmentText('Thanks @bob.');
    expect(seg[1]).toEqual({ kind: 'mention', text: '@bob', value: 'bob' });
    expect(seg[2]).toEqual({ kind: 'text', text: '.' });
  });

  it('treats markup as plain text', () => {
    expect(segmentText('<img src=x onerror=alert(1)>')).toEqual([
      { kind: 'text', text: '<img src=x onerror=alert(1)>' },
    ]);
  });
});
