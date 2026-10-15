export interface LearningReading { id: string; path: string; text: string; truncated: boolean; unavailable?: boolean }
export interface LearningSource { id: string; path: string; role: 'reference' | 'page' | 'commentary'; image: boolean; duration: number | null; has_audio: boolean; width: number | null; height: number | null }
export interface LearningCredit { title: string; creator: string; locator: string }
export interface LearningBlock { id: string; source: string; start: number; end: number; point: string; voice?: string; voice_start?: number }
export interface LearningNote { id: string; text: string; source: string | null; at: number | null; kind: 'thought' | 'quote'; voice_audio?: string }
export interface LearningWorkspace { id: string; title: string; links: string[]; sources: Record<string, LearningSource>; readings?: Record<string, LearningReading>; notes: LearningNote[]; blocks: LearningBlock[]; credits: Record<string, LearningCredit>; script: string; tool_jobs?: { id: string; kind: string }[]; post?: string; updated?: number }
