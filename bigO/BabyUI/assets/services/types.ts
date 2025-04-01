import { AlertColor } from '@mui/material/Alert/Alert';

interface Message {
  message: string;
  level: number;
  level_tag: AlertColor;
}

export type Messages = Message[];

interface Pagination {
  num_pages: number;
  num_records: number;
  num_per_page: number;
  current_page_num: number;
}
interface Search {
  query: string | null;
}
interface Sorting {
  is_asc: boolean | null;
}
interface Column {
  sorting: Sorting | null;
}
export interface ListPage<RecordT, ColumnsT> {
  prefix: string | null;
  pagination: Pagination | null;
  search: Search | null;
  records: RecordT[];
  columns: ColumnsT;
}

export interface UserRecord {
  id: string;
  title: string;
  last_usage_at_repr: string;
  online_status: 'online' | 'offline' | 'never';
  used_bytes: number;
  total_limit_bytes: number;
  expires_in_seconds: string;
}

export interface UserRecordColumns {
  used_bytes?: Column;
}

export interface UrlReverse {
  name: string;
  url: string;
}
