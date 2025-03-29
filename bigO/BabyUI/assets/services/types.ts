import { AlertColor } from '@mui/material/Alert/Alert';

interface Message {
  message: string;
  level: number;
  level_tag: AlertColor;
}

export type Messages = Message[];

export interface ListPage {
  num_pages: number;
  current_page_num: number;
}

export interface Users {
  id: string;
  title: string;
  last_usage_at_repr: string;
  online_status: 'online' | 'offline' | 'never';
  used_bytes: number;
  total_limit_bytes: number;
  expires_in_seconds: string;
}

export interface UsersListPage extends ListPage {
  users: Users[];
}
