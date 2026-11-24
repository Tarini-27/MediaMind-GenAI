export type Category = 'all' | 'recipe' | 'workout' | 'place' | 'learning' | 'other';

export interface Item {
  id: string;
  user_id: string;
  media: string;
  title: string;
  category: string;
  kind: 'image' | 'video';
  thumb: string | null;     // thumbnail file for videos
  tags: string[];
  text: string;                       // OCR / transcript / caption text (empty until Role 2's reader exists)
  fields?: Record<string, unknown>;   // schema-guided extraction (empty until the agents exist)
  confidence?: number | null;
  created_at?: string;
}

export interface AskResult {
  answer: string;
  citations: string[];
  records: Item[];
  blocked: string | null;
}

export interface Proposal {
  id: string;
  action: string;
  payload: {
    user_id: string;
    // library.save (an upload)
    title?: string; category?: string; media?: string;
    kind?: 'image' | 'video'; duration_s?: number; original_name?: string; sha256?: string;
    // library.collect (group items into a named collection)
    name?: string; item_ids?: string[]; item_titles?: string[]; existing?: boolean;
    // library.soft_delete (hide one item; recoverable)
    item_id?: string; thumb?: string | null;
  };
  hash: string;
}

export interface Collection {
  id: string;
  name: string;
  count: number;
}

export interface ProposeResult {
  proposal_id: string;
  hash: string;
  payload: Proposal['payload'];
  status: string;
}
