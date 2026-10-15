// MAS AI requests ask main for permission before any user content leaves the machine.
// The broker receives only an origin and a fixed purpose, never prompts, media or keys.
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { engineSocketPath } from './engineTransport';

export const AI_DATA = {
  analysis: {
    en: 'Text, transcripts, titles and selected reference images, for AI planning and editing.',
    'zh-CN': '文字、逐字稿、标题和选取的参考图，用于 AI 规划与剪辑。',
    fr: 'Textes, transcriptions, titres et images de référence sélectionnées, pour la planification et le montage par IA.',
  },
  transcription: {
    en: 'Audio and transcription hints, for speech recognition.',
    'zh-CN': '音频和识别提示词，用于语音转文字。',
    fr: 'Audio et indications de transcription, pour la reconnaissance vocale.',
  },
  speech: {
    en: 'Narration text and voice instructions, for speech synthesis.',
    'zh-CN': '配音文字和声音指令，用于生成语音。',
    fr: 'Texte de narration et instructions vocales, pour la synthèse vocale.',
  },
  generation: {
    en: 'Prompts and reference images, video or audio, for AI media generation.',
    'zh-CN': '提示词及参考图、视频或音频，用于 AI 媒体生成。',
    fr: 'Instructions et images, vidéos ou audio de référence, pour la génération de médias par IA.',
  },
} as const;
export type AiPurpose = keyof typeof AI_DATA;
export type ConsentRequest = { origin: string; purpose: AiPurpose };
export type ConsentLang = 'en' | 'zh-CN' | 'fr';

export function parseConsent(v: unknown): ConsentRequest | null {
  if (!v || typeof v !== 'object') return null;
  const { origin, purpose } = v as Record<string, unknown>;
  if (typeof origin !== 'string' || origin.length > 512 || typeof purpose !== 'string' || !Object.hasOwn(AI_DATA, purpose)) return null;
  try {
    const u = new URL(origin);
    // Exact normalized origin only: no path, credentials or misleading query fragments in the dialog/store.
    if (!['http:', 'https:'].includes(u.protocol) || u.origin !== origin || u.username || u.password) return null;
    return { origin, purpose: purpose as AiPurpose };
  } catch { return null; }
}

export class AiConsentService {
  readonly token = crypto.randomBytes(24).toString('hex');
  socketPath: string | null = null;
  private server: http.Server | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  private grants = new Set<string>();
  private revision = 0;
  constructor(private o: { file: string; ask: (r: ConsentRequest) => Promise<boolean> }) {
    try {
      const data = JSON.parse(fs.readFileSync(o.file, 'utf8'));
      if (data.version === 1 && Array.isArray(data.grants)) {
        for (const r of data.grants) { const parsed = parseConsent(r); if (parsed) this.grants.add(JSON.stringify(parsed)); }
      }
    } catch { /* missing or damaged grants require fresh permission */ }
  }
  private save() {
    fs.mkdirSync(path.dirname(this.o.file), { recursive: true });
    const tmp = `${this.o.file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ version: 1, grants: [...this.grants].map((s) => JSON.parse(s)) }), { mode: 0o600 });
    fs.renameSync(tmp, this.o.file);
  }
  reset() { this.revision++; this.grants.clear(); this.save(); }
  authorize(r: ConsentRequest): Promise<boolean> {
    const run = this.queue.then(async () => {
      const key = JSON.stringify(r);
      if (this.grants.has(key)) return true;
      const rev = this.revision;
      if (!await this.o.ask(r) || rev !== this.revision) return false;
      this.grants.add(key);
      try { this.save(); } catch { this.grants.delete(key); return false; }
      return true;
    });
    this.queue = run.catch(() => undefined);
    return run;
  }
  start(): Promise<void> {
    const sock = engineSocketPath('rf-consent');
    if (!sock) return Promise.reject(new Error('AI consent requires a Unix socket'));
    this.server = http.createServer((req, res) => void this.handle(req, res));
    return new Promise((resolve, reject) => {
      this.server!.once('error', reject);
      this.server!.listen(sock, () => { fs.chmodSync(sock, 0o600); this.socketPath = sock; resolve(); });
    });
  }
  stop() { this.revision++; this.server?.close(); this.server = null; this.socketPath = null; }
  private async handle(req: http.IncomingMessage, res: http.ServerResponse) {
    const reply = (status: number, allowed = false) => {
      res.writeHead(status, { 'content-type': 'application/json', connection: 'close' });
      res.end(JSON.stringify({ allowed })); req.resume();
    };
    const auth = Buffer.from(String(req.headers.authorization ?? ''));
    const want = Buffer.from(`Bearer ${this.token}`);
    if (auth.length !== want.length || !crypto.timingSafeEqual(auth, want)) return reply(401);
    if (req.method !== 'POST' || req.url !== '/consent' || req.headers.origin) return reply(404);
    try {
      let raw = '';
      for await (const c of req) { raw += c; if (raw.length > 4096) return reply(413); }
      const r = parseConsent(JSON.parse(raw));
      if (!r) return reply(400);
      reply(200, await this.authorize(r));
    } catch { reply(500); }
  }
}
