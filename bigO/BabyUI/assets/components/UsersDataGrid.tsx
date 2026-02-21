import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';
import { router, usePage, Link } from '@inertiajs/react';
import { ListPage, UserRecord, UserRecordColumns } from '../services/types.ts';
import * as React from 'react';
import {
  GridColDef,
  GridFilterModel,
  GridSortModel,
  GridPaginationModel,
  GridRowsProp,
} from '@mui/x-data-grid';
import Chip, { ChipOwnProps } from '@mui/material/Chip';
import AllInclusiveIcon from '@mui/icons-material/AllInclusive';
import { filesize } from 'filesize';
import { LinearProgressProps } from '@mui/material/LinearProgress/LinearProgress';
import { Duration } from 'luxon';
import {
  DataGrid,
  GridToolbar,
  GridPaginationInitialState,
} from '@mui/x-data-grid';

interface Props {
  users_list_page: ListPage<UserRecord, UserRecordColumns>;
}
export default function UsersDataGrid({ users_list_page }: Props) {
  const { url } = usePage();
  let columns: GridColDef[] = [
    {
      field: 'Num',
      headerName: 'Num',
      sortable: false,
      flex: 0.2,
      minWidth: 50,
      renderCell: (params) => {
        let res: number;
        if (users_list_page.pagination) {
          res =
            users_list_page.pagination.num_per_page *
              (users_list_page.pagination.current_page_num - 1) +
            params.api.getRowIndexRelativeToVisibleRows(params.id) +
            1;
        } else {
          res = params.api.getRowIndexRelativeToVisibleRows(params.id) + 1;
        }

        return res;
      },
    },
    {
      field: 'title',
      headerName: 'Title',
      sortable: users_list_page.columns?.title !== undefined,
      flex: 1,
      minWidth: 200,
      renderCell: (params) => {
        let title: number = params.value;
        var parsedUrl = new URL(url, window.location.origin);
        parsedUrl.searchParams.set('profile_id', params.row.id);
        // let link = parse/dUrl
        return <Link href={parsedUrl.href}>{title}</Link>;
      },
    },
    {
      field: 'expiresInSeconds',
      headerName: 'Expires At',
      sortable: users_list_page.columns?.expires_at !== undefined,
      flex: 1,
      minWidth: 200,
      renderCell: (params) => {
        let seconds: number | null = params.value;
        if (seconds === null) {
          return <AllInclusiveIcon sx={{ verticalAlign: 'middle' }}/>
        }
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
    {
      field: 'lastUsageAt',
      headerName: 'Last Usage',
      sortable: users_list_page.columns?.last_usage_at !== undefined,
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
      sortable: users_list_page.columns?.used_bytes !== undefined,
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
      field: 'lastSublinkAt',
      headerName: 'Last Sublink',
      sortable: users_list_page.columns?.last_sublink_at !== undefined,
      flex: 1,
      minWidth: 200,
      renderCell: (params) => {
        let color: ChipOwnProps['color'] = 'secondary';
        let label = params.value;
        return <Chip label={label} color={color} size="small" />;
      },
    },
  ];
  let rows: GridRowsProp = users_list_page.records.map((user) => ({
    id: user.id,
    title: user.title,
    onlineStatus: user.online_status,
    lastUsageAt: user.last_usage_at_repr,
    lastSublinkAt: user.last_sublink_at_repr,
    usedBytes: user.used_bytes,
    totalLimitBytes: user.total_limit_bytes,
    expiresInSeconds: user.expires_in_seconds,
  }));

  const [loading, setLoading] = React.useState(false);

  const setPaginationModel = (model: GridPaginationModel) => {
    setLoading(true);
    let data: any = {};
    data[(users_list_page.prefix || '') + '_page_number'] = model.page + 1;
    data[(users_list_page.prefix || '') + '_per_page'] = model.pageSize;
    router.get(url, data, {
      onFinish: () => setLoading(false),
      preserveScroll: true,
      preserveState: true,
    });
  };
  const setFilterModel = (model: GridFilterModel) => {
    setLoading(true);
    let data: any = {};

    data[(users_list_page.prefix || '') + '_search'] =
      model.quickFilterValues?.join(' ');
    router.get(url, data, {
      onFinish: () => setLoading(false),
      preserveScroll: true,
      preserveState: true,
    });
  };
  const setSortModel = (model: GridSortModel) => {
    setLoading(true);
    let sortQ = '';
    for (const gridSortItem of model) {
      if (sortQ !== '') {
        sortQ += ',';
      }
      let sortFieldName: keyof typeof users_list_page.columns;
      if (gridSortItem.field == 'usage') {
        sortFieldName = 'used_bytes';
      } else if (gridSortItem.field == 'lastSublinkAt') {
        sortFieldName = 'last_sublink_at';
      } else if (gridSortItem.field == 'lastUsageAt') {
        sortFieldName = 'last_usage_at';
      } else if (gridSortItem.field == 'expiresInSeconds') {
        sortFieldName = 'expires_at';
      } else if (gridSortItem.field == 'title') {
        sortFieldName = 'title';
      } else {
        throw new Error('cannot sort for ' + gridSortItem.field);
      }
      sortQ += (gridSortItem.sort == 'desc' ? '-' : '') + sortFieldName;
    }
    let data: any = {};
    data[(users_list_page.prefix || '') + '_sort'] = sortQ;
    router.get(url, data, {
      onFinish: () => setLoading(false),
      preserveScroll: true,
      preserveState: true,
    });
  };
  let sortModel: GridSortModel = [];
  if (users_list_page.columns.used_bytes?.sorting?.is_asc) {
    sortModel = [...sortModel, { field: 'usage', sort: 'asc' }];
  } else if (users_list_page.columns.used_bytes?.sorting?.is_asc === false) {
    sortModel = [...sortModel, { field: 'usage', sort: 'desc' }];
  } else {
    sortModel = [...sortModel, { field: 'usage', sort: null }];
  }

  let pagination: GridPaginationInitialState = users_list_page.pagination
    ? {
        paginationModel: {
          page: users_list_page.pagination.current_page_num - 1,
          pageSize: users_list_page.pagination.num_per_page,
        },
      }
    : {};
  let extra_prop = users_list_page.pagination
    ? { rowCount: users_list_page.pagination.num_records }
    : {};

  return (
    <>
      {/*<CustomizedDataGrid columns={columns} rows={rows} />*/}
      <DataGrid
        columns={columns}
        rows={rows}
        disableColumnResize
        disableColumnFilter
        disableColumnSelector
        disableDensitySelector
        slots={{ toolbar: GridToolbar }}
        slotProps={{
          toolbar: {
            showQuickFilter: users_list_page.search !== null,
            quickFilterProps: { debounceMs: 250 },
            printOptions: { disableToolbarButton: true },
            csvOptions: { disableToolbarButton: true },
          },
        }}
        initialState={{
          pagination: pagination,
          sorting: {
            sortModel: sortModel,
          },
          filter: {
            filterModel: {
              items: [],
              quickFilterValues: users_list_page.search?.query?.split(' '),
            },
          },
        }}
        {...extra_prop}
        pageSizeOptions={[15, 25, 50]}
        density="standard"
        paginationMode="server"
        filterMode="server"
        sortingMode="server"
        onPaginationModelChange={setPaginationModel}
        onFilterModelChange={setFilterModel}
        onSortModelChange={setSortModel}
        loading={loading}
      />
    </>
  );
}
