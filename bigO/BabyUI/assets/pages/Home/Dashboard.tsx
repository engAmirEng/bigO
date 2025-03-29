import type {} from '@mui/x-date-pickers/themeAugmentation';
import type {} from '@mui/x-charts/themeAugmentation';
import type {} from '@mui/x-data-grid-pro/themeAugmentation';
import type {} from '@mui/material/themeCssVarsAugmentation';
import type {} from '@mui/x-tree-view/themeAugmentation';
import { alpha } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import AppNavbar from '../../components/AppNavbar';
import Header from '../../components/Header';
import MainGrid from '../../components/MainGrid';
import SideMenu from '../../components/SideMenu';
import AppTheme from '../../theme/AppTheme';
import {
  chartsCustomizations,
  dataGridCustomizations,
  datePickersCustomizations,
  treeViewCustomizations,
} from '../../theme/customizations';
import { UsersListPage } from '../../services/types.ts';

const xThemeComponents = {
  ...chartsCustomizations,
  ...dataGridCustomizations,
  ...datePickersCustomizations,
  ...treeViewCustomizations,
};

interface Agency {
  id: string;
  name: string;
}
interface Props {
  disableCustomTheme?: boolean;
  current_agency_id: string;
  agencies: Agency[];
  logout_url: string;
  users_list_page: UsersListPage;
}
export default function Dashboard({
  disableCustomTheme,
  current_agency_id,
  agencies,
  logout_url,
  users_list_page,
}: Props) {
  return (
    <AppTheme
      disableCustomTheme={disableCustomTheme}
      themeComponents={xThemeComponents}
    >
      <CssBaseline enableColorScheme />
      <Box sx={{ display: 'flex' }}>
        <SideMenu
          agencies={agencies}
          current_agency_id={current_agency_id}
          logout_url={logout_url}
        />
        <AppNavbar
          agencies={agencies}
          current_agency_id={current_agency_id}
          logout_url={logout_url}
        />
        {/* Main content */}
        <Box
          component="main"
          sx={(theme) => ({
            flexGrow: 1,
            backgroundColor: theme.vars
              ? `rgba(${theme.vars.palette.background.defaultChannel} / 1)`
              : alpha(theme.palette.background.default, 1),
            overflow: 'auto',
          })}
        >
          <Stack
            spacing={2}
            sx={{
              alignItems: 'center',
              mx: 3,
              pb: 5,
              mt: { xs: 8, md: 0 },
            }}
          >
            <Header />
            <MainGrid users_list_page={users_list_page} />
          </Stack>
        </Box>
      </Box>
    </AppTheme>
  );
}
