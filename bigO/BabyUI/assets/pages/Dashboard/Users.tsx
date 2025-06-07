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
import SideMenu from '../../components/SideMenu';
import AppTheme from '../../theme/AppTheme';
import {
  chartsCustomizations,
  dataGridCustomizations,
  datePickersCustomizations,
  treeViewCustomizations,
} from '../../theme/customizations';
import {
  ListPage,
  UserRecord,
  UserRecordColumns,
  UrlReverse,
  PlanRecord,
  UserDetail,
} from '../../services/types.ts';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid2';
import Copyright from '../../internals/components/Copyright.tsx';
import UsersDataGrid from '../../components/UsersDataGrid.tsx';
import UserDialogForm from '../../components/UserForm.tsx';
import { Fab } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import * as React from 'react';
import UserDetailDialog from '../../components/UserDetailDialog.tsx';
import { router, usePage } from '@inertiajs/react';

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
  users_list_page: ListPage<UserRecord, UserRecordColumns>;
  selected_user: UserDetail | null;
  urls: UrlReverse[];
  creatable_plans: PlanRecord[];
}
export default function Users({
  disableCustomTheme,
  current_agency_id,
  agencies,
  logout_url,
  users_list_page,
  selected_user,
  urls,
  creatable_plans,
}: Props) {
  const { url } = usePage();
  var parsedUrl = new URL(url, window.location.origin);
  let period_id = parsedUrl.searchParams.get('period_id');
  const [createFormOpen, setCreateFormOpen] = React.useState(false);
  const [userDetailOpen, setUserDetailOpen] = React.useState(!!period_id);
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
          urls={urls}
        />
        <AppNavbar
          agencies={agencies}
          current_agency_id={current_agency_id}
          logout_url={logout_url}
          urls={urls}
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
            <Header breadCrumb={['Dashboard', 'Users']} />
            <Box sx={{ width: '100%', maxWidth: { sm: '100%', md: '1700px' } }}>
              {/* cards */}
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
                <Typography component="h2" variant="h6" sx={{ mb: 2 }}>
                  Users
                </Typography>
                <Fab
                  size={'medium'}
                  color="secondary"
                  aria-label="add"
                  onClick={() => setCreateFormOpen(true)}
                >
                  <AddIcon />
                </Fab>
              </Stack>
              <UserDialogForm
                isOpen={createFormOpen}
                setOpen={setCreateFormOpen}
                plans={creatable_plans}
              />
              <UserDetailDialog
                isOpen={userDetailOpen}
                onClose={() => {
                  setUserDetailOpen(false);
                  parsedUrl.searchParams.delete('period_id');
                  router.get(parsedUrl.href);
                }}
                user={selected_user}
                creatable_plans={creatable_plans}
              />
              <Grid container spacing={2} columns={12}>
                <UsersDataGrid users_list_page={users_list_page} />
              </Grid>
              <Copyright sx={{ my: 4 }} />
            </Box>
          </Stack>
        </Box>
      </Box>
    </AppTheme>
  );
}
