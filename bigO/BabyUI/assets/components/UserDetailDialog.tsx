import { router, usePage } from '@inertiajs/react';
import QRCode from 'qrcode';
import Card from '@mui/material/Card';
import CardMedia from '@mui/material/CardMedia';
import {
  Box,
  Button,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogContentText,
  Dialog,
  Tab,
  CircularProgress,
  CardHeader,
  Fab,
} from '@mui/material';
import { TabContext, TabList, TabPanel } from '@mui/lab';

import * as React from 'react';
import { PlanRecord, UserDetail } from '../services/types.ts';
import CheckIcon from '@mui/icons-material/Check';
import ClearIcon from '@mui/icons-material/Clear';
import ReplayIcon from '@mui/icons-material/Replay';
import ContentCopyTwoToneIcon from '@mui/icons-material/ContentCopyTwoTone';
import Stack from '@mui/material/Stack';
import UserRenewDialogForm from './UserRenewForm.tsx';
interface Props {
  isOpen: boolean;
  onClose: () => void;
  user: UserDetail | null;
  creatable_plans: PlanRecord[];
}

export default function UserDetailDialog({
  isOpen,
  onClose,
  user,
  creatable_plans,
}: Props) {
  let {
    url,
    props: { errors },
  } = usePage();
  console.log(user);
  if (!user) {
    return (
      <Dialog open={isOpen} onClose={() => onClose()}>
        <DialogTitle>Create New Profile</DialogTitle>

        <DialogContent>
          <p>not found</p>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => onClose()}>Cancel</Button>

          <Button onClick={() => {}} variant="contained"></Button>
        </DialogActions>
      </Dialog>
    );
  }
  const [currentTab, setCurrentTab] = React.useState('1');
  const [suspending, setSuspending] = React.useState(false);
  const [renewFormOpen, setrenewFormOpen] = React.useState(false);
  const handleChange = (event: React.SyntheticEvent, newValue: string) => {
    setCurrentTab(newValue);
  };

  const [qr, setQr] = React.useState('');
  const [b64qr, setB64Qr] = React.useState('');

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
      alert('Copied!');
    } catch (err) {
      alert('Copy failed');
    }
  };

  const [suspendDialogOpen, setSuspendDialogOpen] = React.useState(false);

  let suspendUnSuspend = null;
  if (suspending) {
    suspendUnSuspend = (
      <Button variant="outlined" color="error">
        <CircularProgress />
      </Button>
    );
  } else {
    suspendUnSuspend = user.is_suspended ? (
      <Button
        variant="outlined"
        color="error"
        startIcon={<CheckIcon />}
        onClick={() => setSuspendDialogOpen(true)}
      >
        UnSuspend
      </Button>
    ) : (
      <Button
        variant="outlined"
        color="error"
        startIcon={<ClearIcon />}
        onClick={() => setSuspendDialogOpen(true)}
      >
        Suspend
      </Button>
    );
  }

  return (
    <Dialog fullWidth open={isOpen} onClose={() => onClose()}>
      <DialogTitle>{user.title}</DialogTitle>

      <DialogContent sx={{ px: 1 }}>
        <TabContext value={currentTab}>
          <Dialog
            open={suspendDialogOpen}
            onClose={() => setSuspendDialogOpen(false)}
            aria-labelledby="alert-dialog-title"
            aria-describedby="alert-dialog-description"
          >
            <DialogTitle id="alert-dialog-title">
              {user.is_suspended ? 'Unsuspend User?' : 'Suspend User?'}
            </DialogTitle>
            <DialogContent>
              <DialogContentText id="alert-dialog-description"></DialogContentText>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setSuspendDialogOpen(false)}>
                Disagree
              </Button>
              <Button
                onClick={() => {
                  let data = new FormData();
                  if (user.is_suspended) {
                    data.append('action', 'unsuspend');
                  } else {
                    data.append('action', 'suspend');
                  }
                  setSuspending(true);
                  router.post(url, data, {
                    onFinish: () => setSuspending(false),
                  });
                  setSuspendDialogOpen(false);
                }}
                autoFocus
              >
                Agree
              </Button>
            </DialogActions>
          </Dialog>
          <UserRenewDialogForm
            isOpen={renewFormOpen}
            setOpen={setrenewFormOpen}
            plans={creatable_plans}
            current_plan={user.plan}
          />
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <TabList onChange={handleChange} aria-label="lab API tabs example">
              <Tab label="Overview" value="1" />
              <Tab label="Links" value="2" />
              <Tab label="History" value="3" />
            </TabList>
          </Box>

          <TabPanel value="1">
            <p>Created At: {user.created_at_str}</p>
            <Button
              variant="contained"
              color="success"
              startIcon={<ReplayIcon />}
              onClick={() => setrenewFormOpen(true)}
            >
              Renew
            </Button>
            {suspendUnSuspend}
          </TabPanel>
          <TabPanel sx={{ px: 0 }} value="2">
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
                <CardHeader title={'Android'} />
                <Fab
                  size={'medium'}
                  color="secondary"
                  aria-label="add"
                  onClick={() => handleCopy(user.sublink.normal)}
                >
                  <ContentCopyTwoToneIcon />
                </Fab>
              </Stack>
              <CardMedia
                sx={{
                  width: '100%',
                  height: '100%',
                  aspectRatio: '1/1',
                  maxHeight: '60dvh',
                  maxWidth: '60dvh',
                  mx: 'auto',
                }}
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
                <CardHeader title={'IOS'} />
                <Fab
                  size={'medium'}
                  color="secondary"
                  aria-label="add"
                  onClick={() => handleCopy(user.sublink.normal)}
                >
                  <ContentCopyTwoToneIcon />
                </Fab>
              </Stack>
              <CardMedia
                sx={{
                  width: '100%',
                  height: '100%',
                  aspectRatio: '1/1',
                  maxHeight: '60dvh',
                  maxWidth: '60dvh',
                  mx: 'auto',
                }}
                image={qr}
              />
            </Card>
          </TabPanel>
          <TabPanel value="3">
            {user.events.map((event) => (
              <p>
                {event.title} at {event.created_at_str}
              </p>
            ))}
          </TabPanel>
        </TabContext>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onClose()}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
