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
  last_sublink_at_repr: string | null;
  last_usage_at_repr: string | null;
  online_status: 'online' | 'offline' | 'never';
  used_bytes: number;
  total_limit_bytes: number;
  expires_in_seconds: string;
}

export interface UserRecordColumns {
  used_bytes?: Column;
  last_sublink_at?: Column;
  last_usage_at?: Column;
  expires_at?: Column;
}

export interface UrlReverse {
  name: string;
  url: string;
}

export enum PlanProvider {
  SimpleStrict1 = "type_simple_strict1",
  TypeSimpleDynamic1 = "type_simple_dynamic1",
}

export interface PlanRecord {
  id: string
  name: string;
  plan_provider_key: PlanProvider;
  plan_provider_args: any;
  remained_cap: number;
}
