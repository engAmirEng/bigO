import Avatar from '@mui/material/Avatar';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer, { drawerClasses } from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import NotificationsRoundedIcon from '@mui/icons-material/NotificationsRounded';
import MenuButton from './MenuButton';
import MenuContent from './MenuContent';
import CardAlert from './CardAlert';
import viteLogo from '/vite.jpg';
import Box from '@mui/material/Box';
import SelectContent from './SelectContent.tsx';
import { router } from '@inertiajs/react';
import * as React from 'react';

interface Agency {
  id: string;
  name: string;
}
interface Props {
  open: boolean | undefined;
  toggleDrawer: (newOpen: boolean) => () => void;
  current_agency_id: string;
  agencies: Agency[];
  logout_url: string;
}

export default function SideMenuMobile({
  open,
  toggleDrawer,
  current_agency_id,
  agencies,
  logout_url,
}: Props) {
  let [isLoggingOut, setIsLoggingOut] = React.useState(false);
  const handleLogOut = () => {
    setIsLoggingOut(true);
    router.post(logout_url);
  };
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={toggleDrawer(false)}
      sx={{
        zIndex: (theme) => theme.zIndex.drawer + 1,
        [`& .${drawerClasses.paper}`]: {
          backgroundImage: 'none',
          backgroundColor: 'background.paper',
        },
      }}
    >
      <Stack
        sx={{
          maxWidth: '70dvw',
          height: '100%',
        }}
      >
        <Stack direction="row" sx={{ p: 2, pb: 0, gap: 1 }}>
          <Stack
            direction="row"
            sx={{ gap: 1, alignItems: 'center', flexGrow: 1, p: 1 }}
          >
            <Avatar
              sizes="small"
              alt="Riley Carter"
              src={viteLogo}
              sx={{ width: 24, height: 24 }}
            />
            <Typography component="p" variant="h6">
              Riley Carter
            </Typography>
          </Stack>
          <MenuButton showBadge>
            <NotificationsRoundedIcon />
          </MenuButton>
        </Stack>
        <Divider />
        <Stack sx={{ flexGrow: 1 }}>
          <Box
            sx={{
              display: 'flex',
              mt: 'calc(var(--template-frame-height, 0px) + 4px)',
              p: 1.5,
            }}
          >
            <SelectContent
              agencies={agencies}
              current_agency_id={current_agency_id}
            />
          </Box>
          <Divider />
          <MenuContent />
          <Divider />
        </Stack>
        <CardAlert />
        <Stack sx={{ p: 2 }}>
          <Button
            variant="outlined"
            fullWidth
            startIcon={<LogoutRoundedIcon />}
            onClick={handleLogOut}
            disabled={isLoggingOut}
          >
            {isLoggingOut ? 'logging you out ...' : 'Logout'}
          </Button>
        </Stack>
      </Stack>
    </Drawer>
  );
}
