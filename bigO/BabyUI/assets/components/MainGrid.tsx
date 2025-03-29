import Grid from '@mui/material/Grid2';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';
import Copyright from '../internals/components/Copyright';
import ChartUserByCountry from './ChartUserByCountry';
import CustomizedTreeView from './CustomizedTreeView';
import HighlightedCard from './HighlightedCard';
import PageViewsBarChart from './PageViewsBarChart';
import SessionsChart from './SessionsChart';
import StatCard, { StatCardProps } from './StatCard';
import { UsersListPage } from '../services/types.ts';
import { GridColDef, GridRowsProp } from '@mui/x-data-grid';
import Chip, { ChipOwnProps } from '@mui/material/Chip';
import { filesize } from 'filesize';
import { LinearProgressProps } from '@mui/material/LinearProgress/LinearProgress';
import { Duration } from 'luxon';
import { DataGrid } from '@mui/x-data-grid';

const data: StatCardProps[] = [
  {
    title: 'Users',
    value: '14k',
    interval: 'Last 30 days',
    trend: 'up',
    data: [
      200, 24, 220, 260, 240, 380, 100, 240, 280, 240, 300, 340, 320, 360, 340,
      380, 360, 400, 380, 420, 400, 640, 340, 460, 440, 480, 460, 600, 880, 920,
    ],
  },
  {
    title: 'Conversions',
    value: '325',
    interval: 'Last 30 days',
    trend: 'down',
    data: [
      1640, 1250, 970, 1130, 1050, 900, 720, 1080, 900, 450, 920, 820, 840, 600,
      820, 780, 800, 760, 380, 740, 660, 620, 840, 500, 520, 480, 400, 360, 300,
      220,
    ],
  },
  {
    title: 'Event count',
    value: '200k',
    interval: 'Last 30 days',
    trend: 'neutral',
    data: [
      500, 400, 510, 530, 520, 600, 530, 520, 510, 730, 520, 510, 530, 620, 510,
      530, 520, 410, 530, 520, 610, 530, 520, 610, 530, 420, 510, 430, 520, 510,
    ],
  },
];
interface Props {
  users_list_page: UsersListPage;
}
export default function MainGrid({ users_list_page }: Props) {
  let columns: GridColDef[] = [
    {
      field: 'title',
      headerName: 'Title',
      flex: 1,
      minWidth: 200,
    },
    {
      field: 'lastUsageAt',
      headerName: 'Last Usage',
      flex: 1,
      minWidth: 200,
      renderCell: (params) => {
        let color: ChipOwnProps['color'];
        let label;
        if (params.row.onlineStatus == 'never') {
          color = 'error';
          label = 'never';
        } else if (params.row.onlineStatus == 'online') {
          color = 'success';
          label = 'online';
        } else {
          color = 'secondary';
          label = params.value;
        }
        return <Chip label={label} color={color} size="small" />;
      },
    },
    {
      field: 'usage',
      headerName: 'Usage',
      flex: 1,
      minWidth: 200,
      renderCell: (params) => {
        let percentage = Math.round(
          (params.row.usedBytes / params.row.totalLimitBytes) * 100
        );
        let color: LinearProgressProps['color'];
        if (percentage > 85) {
          color = 'error';
        } else if (percentage > 65) {
          color = 'warning';
        } else {
          color = 'success';
        }
        return (
          <Box
            sx={{
              height: '100%',
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <LinearProgress
              variant="determinate"
              value={percentage}
              color={color}
              sx={{ height: 20, width: '100%', borderRadius: 5 }}
            />
            <Typography
              variant="caption"
              sx={{
                position: 'absolute',
                width: '100%',
                textAlign: 'center',
                fontWeight: 'bold',
                color: percentage > 50 ? 'white' : 'black',
              }}
            >
              {`${filesize(params.row.usedBytes)}/${filesize(params.row.totalLimitBytes)}`}
            </Typography>
          </Box>
        );
      },
    },
    {
      field: 'expiresInSeconds',
      headerName: 'Expires At',
      flex: 1,
      minWidth: 200,
      renderCell: (params) => {
        let seconds: number = params.value;
        let isPast = false;
        if (seconds < 0) {
          seconds *= -1;
          isPast = true;
        }
        let duration = Duration.fromObject({ seconds: seconds });
        if (duration.shiftTo('hours').hours > 25) {
          duration = duration.shiftTo('days', 'hours');
        } else if (duration.shiftTo('hours').hours > 10) {
          duration = duration.shiftTo('hours');
        } else {
          duration = duration.shiftTo('hours', 'minutes');
        }
        return (
          <Chip
            label={
              duration.toHuman({ listStyle: 'long' }) + (isPast ? ' ago' : '')
            }
            color={isPast ? 'error' : 'primary'}
            size="small"
          />
        );
      },
    },
  ];
  console.log(users_list_page);
  let rows: GridRowsProp = users_list_page.users.map((user) => ({
    id: user.id,
    title: user.title,
    onlineStatus: user.online_status,
    lastUsageAt: user.last_usage_at_repr,
    usedBytes: user.used_bytes,
    totalLimitBytes: user.total_limit_bytes,
    expiresInSeconds: user.expires_in_seconds,
  }));

  return (
    <Box sx={{ width: '100%', maxWidth: { sm: '100%', md: '1700px' } }}>
      {/* cards */}
      <Typography component="h2" variant="h6" sx={{ mb: 2 }}>
        Overview
      </Typography>
      <Grid
        container
        spacing={2}
        columns={12}
        sx={{ mb: (theme) => theme.spacing(2) }}
      >
        {data.map((card, index) => (
          <Grid key={index} size={{ xs: 12, sm: 6, lg: 3 }}>
            <StatCard {...card} />
          </Grid>
        ))}
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <HighlightedCard />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <SessionsChart />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <PageViewsBarChart />
        </Grid>
      </Grid>
      <Typography component="h2" variant="h6" sx={{ mb: 2 }}>
        Users
      </Typography>
      <Grid container spacing={2} columns={12}>
        <Grid size={{ xs: 12, lg: 9 }}>
          {/*<CustomizedDataGrid columns={columns} rows={rows} />*/}
          <DataGrid
            columns={columns}
            rows={rows}
            disableColumnResize
            initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
            pageSizeOptions={[25, 50]}
            density="standard"
          />
        </Grid>
        <Grid size={{ xs: 12, lg: 3 }}>
          <Stack gap={2} direction={{ xs: 'column', sm: 'row', lg: 'column' }}>
            <CustomizedTreeView />
            <ChartUserByCountry />
          </Stack>
        </Grid>
      </Grid>
      <Copyright sx={{ my: 4 }} />
    </Box>
  );
}
