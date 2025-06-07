import { router, usePage } from '@inertiajs/react';
import QRCode from 'qrcode';
import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import CardContent from '@mui/material/CardContent';
import CardMedia from '@mui/material/CardMedia';
import {
  Typography,
  Box,
  FormControl,
  TextField,
  FormHelperText,
  Button,
  DialogTitle,
  DialogContent,
  InputAdornment,
  DialogActions,
  Dialog,
  Tab,
  InputLabel,
  MenuItem,
  Select,
  SelectChangeEvent,
  OutlinedInput, CircularProgress, CardHeader, Fab,
} from '@mui/material';
import {TabContext, TabList, TabPanel} from '@mui/lab';

import * as React from 'react';
import {PlanProvider, PlanRecord, UserDetail} from '../services/types.ts';
import AddIcon from '@mui/icons-material/Add';
import ClearIcon from '@mui/icons-material/Clear';
import ToggleOffIcon from '@mui/icons-material/ToggleOff';
import EditIcon from '@mui/icons-material/Edit';
import ReplayIcon from '@mui/icons-material/Replay';
import ContentCopyTwoToneIcon from '@mui/icons-material/ContentCopyTwoTone';
import Stack from "@mui/material/Stack";
interface Props {
  isOpen: boolean;
  onClose: () => void;
  user: UserDetail | null;
}

export default function UserDetailDialog({ isOpen, onClose, user }: Props) {
  let {
    url,
    props: { errors },
  } = usePage();
  console.log(user)
  if (!user) {
    return <Dialog open={isOpen} onClose={() => onClose()}>
      <DialogTitle>Create New Profile</DialogTitle>

      <DialogContent>
        <p>not found</p>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onClose()}>Cancel</Button>

        <Button onClick={() => {
        }} variant="contained">
        </Button>
      </DialogActions>
    </Dialog>
  }
  const [value, setValue] = React.useState('1');
  const handleChange = (event: React.SyntheticEvent, newValue: string) => {
    setValue(newValue);
  };

  const [qr, setQr] = React.useState('');
  const [b64qr, setB64Qr] = React.useState('');
  console.log(user)

  React.useEffect(() => {
    QRCode.toDataURL(user.sublink.normal)
      .then((url) => setQr(url))
      .catch((err) => console.error(err));
  }, []);

  React.useEffect(() => {
    QRCode.toDataURL(user.sublink.b64)
      .then((url) => setB64Qr(url))
      .catch((err) => console.error(err));
  }, []);
  const handleCopy = async (txt) => {
    try {
      await navigator.clipboard.writeText(txt);
      alert("Copied!");
    } catch (err) {
      alert("Copy failed");
    }
  };

  return (
    <Dialog fullWidth open={isOpen} onClose={() => onClose()}>
      <DialogTitle>{user.title}</DialogTitle>

      <DialogContent sx={{px: 1}}>
        <TabContext value={value}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <TabList onChange={handleChange} aria-label="lab API tabs example">
            <Tab label="Overview" value="1" />
            <Tab label="Links" value="2" />
          </TabList>
        </Box>

        <TabPanel value="1">
          <p>Created At: {user.created_at_str}</p>
          <Button variant="contained" color="success" startIcon={<ReplayIcon />}>
            Renew
          </Button>
          <Button variant="contained" color="secondary" startIcon={<EditIcon />}>
            Edit
          </Button>
          <Button variant="outlined" color="error" startIcon={<ClearIcon />}>
            Suspend
          </Button>
        </TabPanel>
          <TabPanel sx={{px: 0}} value="2">
          <Card>
            <Stack
                direction="row"
                sx={{
                  width: '100%',
                  alignItems: 'center',
                  justifyContent: 'flex-start',
                }}
                spacing={2}
                mb={1}
              >
                <CardHeader title={"Android"}/>
                <Fab size={"medium"} color="secondary" aria-label="add" onClick={() => handleCopy(user.sublink.normal)}>
                  <ContentCopyTwoToneIcon />
                </Fab>
              </Stack>
            <CardMedia
              sx={{ width: "100%", height: "100%", aspectRatio: "1/1", maxHeight: "60dvh", maxWidth: "60dvh", mx: "auto" }}
              image={qr}
            />
          </Card>
          <Card>
            <Stack
                direction="row"
                sx={{
                  width: '100%',
                  alignItems: 'center',
                  justifyContent: 'flex-start',
                }}
                spacing={2}
                mb={1}
              >
                <CardHeader title={"IOS"}/>
                <Fab size={"medium"} color="secondary" aria-label="add" onClick={() => handleCopy(user.sublink.normal)}>
                  <ContentCopyTwoToneIcon />
                </Fab>
              </Stack>
            <CardMedia
              sx={{ width: "100%", height: "100%", aspectRatio: "1/1", maxHeight: "60dvh", maxWidth: "60dvh", mx: "auto" }}
              image={qr}
            />
          </Card>

      </TabPanel>
      </TabContext>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onClose()}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
