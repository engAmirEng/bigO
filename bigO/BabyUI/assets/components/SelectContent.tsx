import MuiAvatar from '@mui/material/Avatar';
import MuiListItemAvatar from '@mui/material/ListItemAvatar';
import MenuItem from '@mui/material/MenuItem';
import ListItemText from '@mui/material/ListItemText';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListSubheader from '@mui/material/ListSubheader';
import Select, { SelectChangeEvent, selectClasses } from '@mui/material/Select';
import Divider from '@mui/material/Divider';
import { styled } from '@mui/material/styles';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import SmartphoneRoundedIcon from '@mui/icons-material/SmartphoneRounded';
import ConstructionRoundedIcon from '@mui/icons-material/ConstructionRounded';
import type {} from '@mui/material/themeCssVarsAugmentation';
import { router, usePage } from '@inertiajs/react';

const Avatar = styled(MuiAvatar)(({ theme }) => ({
  width: 28,
  height: 28,
  backgroundColor: (theme.vars || theme).palette.background.paper,
  color: (theme.vars || theme).palette.text.secondary,
  border: `1px solid ${(theme.vars || theme).palette.divider}`,
}));

const ListItemAvatar = styled(MuiListItemAvatar)({
  minWidth: 0,
  marginRight: 12,
});

interface Agency {
  id: string;
  name: string;
}
interface Props {
  current_agency_id: string;
  agencies: Agency[];
}
export default function SelectContent({ agencies, current_agency_id }: Props) {
  const { url } = usePage();
  const handleChange = (event: SelectChangeEvent) => {
    let data = new FormData();
    data.append('set_to_agency_id', event.target.value);
    router.post(url, data);
  };

  return (
    <Select
      labelId="company-select"
      id="company-simple-select"
      value={current_agency_id}
      onChange={handleChange}
      displayEmpty
      inputProps={{ 'aria-label': 'Select company' }}
      fullWidth
      sx={{
        maxHeight: 56,
        width: 215,
        '&.MuiList-root': {
          p: '8px',
        },
        [`& .${selectClasses.select}`]: {
          display: 'flex',
          alignItems: 'center',
          gap: '2px',
          pl: 1,
        },
      }}
    >
      <ListSubheader sx={{ pt: 0 }}>Production</ListSubheader>
      {agencies.map((agency) => {
        return (
          <MenuItem key={agency.id} value={agency.id}>
            <ListItemAvatar>
              <Avatar alt="Sitemark App">
                <SmartphoneRoundedIcon sx={{ fontSize: '1rem' }} />
              </Avatar>
            </ListItemAvatar>
            <ListItemText
              primary={agency.name}
              secondary="Mobile application"
            />
          </MenuItem>
        );
      })}

      <ListSubheader>Development</ListSubheader>
      <MenuItem value={30}>
        <ListItemAvatar>
          <Avatar alt="Sitemark Store">
            <ConstructionRoundedIcon sx={{ fontSize: '1rem' }} />
          </Avatar>
        </ListItemAvatar>
        <ListItemText primary="Sitemark-Admin" secondary="Web app" />
      </MenuItem>
      <Divider sx={{ mx: -1 }} />
      <MenuItem value={40}>
        <ListItemIcon>
          <AddRoundedIcon />
        </ListItemIcon>
        <ListItemText primary="Add product" secondary="Web app" />
      </MenuItem>
    </Select>
  );
}
