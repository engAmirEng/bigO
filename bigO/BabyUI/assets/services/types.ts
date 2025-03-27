import { AlertColor } from '@mui/material/Alert/Alert';

interface Message {
  message: string;
  level: number;
  level_tag: AlertColor;
}

export type Messages = Message[];
