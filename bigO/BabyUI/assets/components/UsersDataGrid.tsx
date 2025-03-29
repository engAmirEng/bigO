import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';
import { router, usePage } from '@inertiajs/react';
import { UsersListPage } from '../services/types.ts';
import * as React from 'react';
import {
  GridColDef,
  GridPaginationModel,
  GridRowsProp,
} from '@mui/x-data-grid';
import Chip, { ChipOwnProps } from '@mui/material/Chip';
import { filesize } from 'filesize';
import { LinearProgressProps } from '@mui/material/LinearProgress/LinearProgress';
import { Duration } from 'luxon';
import { DataGrid } from '@mui/x-data-grid';

interface Props {
  users_list_page: UsersListPage;
}
export default function UsersDataGrid({ users_list_page }: Props) {
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
  const { url } = usePage();
  const [loading, setloading] = React.useState(false);

  const setPaginationModel = (
    model: GridPaginationModel,
    details: GridCallbacllDetails
  ) => {
    model.pageSize;
    setloading(true);
    router.get(url, { page: model.page + 1, pageSize: model.pageSize });
  };

  return (
    <>
      {/*<CustomizedDataGrid columns={columns} rows={rows} />*/}
      <DataGrid
        columns={columns}
        rows={rows}
        disableColumnResize
        initialState={{
          pagination: {
            paginationModel: {
              page: users_list_page.current_page_num - 1,
              pageSize: users_list_page.num_per_page,
            },
          },
        }}
        rowCount={users_list_page.num_records}
        pageSizeOptions={[15, 25, 50]}
        density="standard"
        paginationMode="server"
        filterMode="server"
        sortingMode="server"
        onPaginationModelChange={setPaginationModel}
        loading={loading}
      />
    </>
  );
}
