import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import HomeRoundedIcon from '@mui/icons-material/HomeRounded';
import PeopleRoundedIcon from '@mui/icons-material/PeopleRounded';
import SettingsRoundedIcon from '@mui/icons-material/SettingsRounded';
import InfoRoundedIcon from '@mui/icons-material/InfoRounded';
import HelpRoundedIcon from '@mui/icons-material/HelpRounded';
import { Link, usePage } from '@inertiajs/react';
import { UrlReverse } from '../services/types.ts';

// const mainListItems = [
//   { text: 'Home', icon: <HomeRoundedIcon /> },
//   { text: 'Analytics', icon: <AnalyticsRoundedIcon /> },
//   { text: 'Clients', icon: <PeopleRoundedIcon /> },
//   { text: 'Tasks', icon: <AssignmentRoundedIcon /> },
// ];

const secondaryListItems = [
  { text: 'Settings', icon: <SettingsRoundedIcon /> },
  { text: 'About', icon: <InfoRoundedIcon /> },
  { text: 'Feedback', icon: <HelpRoundedIcon /> },
];
interface Props {
  urls: UrlReverse[];
}
export default function MenuContent({ urls }: Props) {
  const { url } = usePage();
  let dashboard_home_url = urls.filter(
    (a) => a.name == 'BabyUI:dashboard_home'
  )[0].url;
  let dashboard_users_url = urls.filter(
    (a) => a.name == 'BabyUI:dashboard_users'
  )[0].url;
  const pathname = new URL(url, window.location.origin).pathname;
  return (
    <Stack sx={{ flexGrow: 1, p: 1, justifyContent: 'space-between' }}>
      <List dense>
        <ListItem disablePadding sx={{ display: 'block' }}>
          <ListItemButton
            selected={pathname === dashboard_home_url}
            component={Link}
            href={dashboard_home_url}
          >
            <ListItemIcon>
              <HomeRoundedIcon />
            </ListItemIcon>
            <ListItemText primary="Home" />
          </ListItemButton>
        </ListItem>
        <ListItem disablePadding sx={{ display: 'block' }}>
          <ListItemButton
            selected={pathname === dashboard_users_url}
            component={Link}
            href={dashboard_users_url}
          >
            <ListItemIcon>
              <PeopleRoundedIcon />
            </ListItemIcon>
            <ListItemText primary="Users" />
          </ListItemButton>
        </ListItem>
      </List>
      <List dense>
        {secondaryListItems.map((item, index) => (
          <ListItem key={index} disablePadding sx={{ display: 'block' }}>
            <ListItemButton>
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Stack>
  );
}
