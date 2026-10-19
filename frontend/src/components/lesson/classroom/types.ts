export type ClassroomBeatKind =
  | 'intro'
  | 'explanation'
  | 'key_point'
  | 'example'
  | 'vocabulary'
  | 'closing'

export type LectureSegmentKind =
  | 'hook'
  | 'concept'
  | 'example_walkthrough'
  | 'contrast'
  | 'vocab_spotlight'
  | 'cfu'
  | 'summary'
  | 'handoff'

export type ClassroomAnnotationType = 'highlight' | 'margin_note' | 'underline'

export type ClassroomClarifyAction = 'rephrase' | 'more_examples'

export interface ClassroomBeat {
  id: string
  kind: ClassroomBeatKind
  title: string | null
  primary_text: string
  secondary_text: string | null
  narration_text: string
}

export interface ClassroomDeck {
  lesson_id: number
  study_plan_id: number
  target_language: string
  title: string
  cefr_level: string
  lesson_type: string
  beats: ClassroomBeat[]
}

export interface LectureSegment {
  id: string
  order: number
  kind: LectureSegmentKind
  speech_text: string
  slide_id: string
  annotation_event_ids: string[]
}

export interface SlideFrame {
  id: string
  title: string
  bullets: string[]
  callout: string | null
  reveal_steps: number
}

export interface AnnotationEvent {
  id: string
  segment_id: string
  at: 'segment_start' | 'speech_fraction'
  speech_fraction: number | null
  op: 'highlight' | 'underline' | 'margin_note' | 'clear'
  target_field: 'title' | 'callout' | 'bullet'
  target_index: number | null
  substring: string | null
  payload: string
}

export interface ClassroomPack {
  lesson_id: number
  study_plan_id: number
  target_language: string
  title: string
  cefr_level: string
  lesson_type: string
  content_hash: string
  generator_version: string
  segments: LectureSegment[]
  slides: SlideFrame[]
  annotations: AnnotationEvent[]
}

export interface ClassroomSessionResponse {
  status: 'ready' | 'generating' | 'fallback'
  mode: 'lecture' | 'reading'
  pack: ClassroomPack | null
  fallback_deck: ClassroomDeck | null
  preparing: boolean
}

export interface ClassroomPackStatusResponse {
  status: 'ready' | 'generating' | 'missing' | 'failed'
  pack: ClassroomPack | null
}

export interface ClassroomAnnotationOp {
  beat_id: string
  type: ClassroomAnnotationType
  payload: string
  target_field?: 'title' | 'callout' | 'bullet' | 'primary'
  target_index?: number | null
}

export interface ClassroomClarifyResponse {
  spoken_text: string
  display_text: string
  annotations: ClassroomAnnotationOp[]
}
