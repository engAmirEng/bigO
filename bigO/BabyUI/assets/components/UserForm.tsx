import { router, usePage } from '@inertiajs/react';
import {
  Typography,
  Box,
  FormControl,
  TextField,
  FormLabel,
  Button,
  DialogTitle,
  DialogContent,
  InputAdornment,
  DialogActions,
  Dialog,
  InputLabel,
  MenuItem,
  Select,
  SelectChangeEvent,
  OutlinedInput,
} from '@mui/material';
import * as React from 'react';
import { PlanProvider, PlanRecord } from '../services/types.ts';
interface Props {
  isOpen: boolean;
  setOpen: () => {};
  plans: PlanRecord[];
}

export default function UserDialogForm({ isOpen, setOpen, plans }: Props) {
  let {
    url,
    props: { errors },
  } = usePage();
  errors = errors || {};
  let titleErrorMessage = errors.title;
  let planErrorMessage = errors.plan;
  // let ErrorMessage = errors.plan;
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    console.log(data);
    const dataf = Object.fromEntries(data.entries());
    console.log(dataf)
    router.post(url, data);
  };

  const [currentPlanID, setCurrentPlanID] = React.useState<string>('');

  const handleChangePlan = (event: SelectChangeEvent<typeof currentPlanID>) => {
    const {
      target: { value },
    } = event;
    setCurrentPlanID(value);
  };

  let currentPlan: PlanRecord | undefined = undefined;
  let planSpecificInputParts = null;
  if (currentPlanID) {
    currentPlan = plans.find((plan) => plan.id == currentPlanID);
  }

  if (currentPlan) {
    if (currentPlan.plan_provider_key == PlanProvider.TypeSimpleDynamic1) {
      planSpecificInputParts = (
        <>
          <FormControl>
            <TextField
              // error={titleErrorMessage}
              // helperText={titleErrorMessage}
              name="expiery_days"
              type="number"
              label="Expiry"
              id="expiery_days"
              required
              fullWidth
              slotProps={{
                input: {
                  endAdornment: (
                    <InputAdornment position="start">day</InputAdornment>
                  ),
                },
              }}
              variant="outlined"
              color={titleErrorMessage ? 'error' : 'primary'}
            />
          </FormControl>
          <FormControl>
            <TextField
              // error={'passwordError'}
              // helperText={'passwordError'}
              label={'Volume'}
              name="volume_gb"
              type="number"
              id="volume_gb"
              required
              fullWidth
              slotProps={{
                input: {
                  endAdornment: (
                    <InputAdornment position="start">GB</InputAdornment>
                  ),
                },
              }}
              variant="outlined"
              color={'passwordError' ? 'error' : 'primary'}
            />
          </FormControl>

        </>
      );
    }
  }
  const formRef = React.useRef();
  return (
    <Dialog open={isOpen} onClose={() => setOpen(false)}>
      <DialogTitle>Create New Profile</DialogTitle>

      <DialogContent>
        <Box
          component="form"
          ref={formRef}
          onSubmit={handleSubmit}
          noValidate
          sx={{
            display: 'flex',
            flexDirection: 'column',
            width: '100%',
            gap: 2,
          }}
        >
          <Typography color="info" sx={{ mt: 1 }}>
            If want to create a new profile for an old user then just use the
            action button
          </Typography>

          <Typography color="error" sx={{ mt: 1 }}>
            {errors.__all__}
          </Typography>

          <FormControl>
            <TextField
              error={titleErrorMessage}
              helperText={titleErrorMessage}
              name="title"
              label="ffTitle"
              id="title"
              autoComplete="current-password"
              required
              fullWidth
              variant="outlined"
              color={titleErrorMessage ? 'error' : 'primary'}
            />
          </FormControl>
          <FormControl>
            <InputLabel htmlFor="plan" shrink>
              Plan
            </InputLabel>
            <Select
              displayEmpty
              value={currentPlanID}
              name="plan"
              id="plan"
              variant="outlined"
              fullWidth
              onChange={handleChangePlan}
              input={<OutlinedInput />}
              renderValue={(selected) => {
                if (!selected) {
                  return <em>Select a Plan</em>;
                }
                let selectedPlan = plans.find((plan) => plan.id == selected);
                if (selectedPlan == undefined) {
                  throw new Error();
                }
                return selectedPlan.name;
              }}
            >
              <MenuItem disabled value="">
                {plans.length ? (
                  <em>Select a Plan</em>
                ) : (
                  <em>There is no active Plans for you</em>
                )}
              </MenuItem>
              {plans.map((plan) => (
                <MenuItem key={plan.id} value={plan.id} title={plan.name}>
                  {plan.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {planSpecificInputParts}
          {/*<FormControlLabel*/}
          {/*  control={<Checkbox value="remember" color="primary" />}*/}
          {/*  label="Remember me"*/}
          {/*/>*/}
          {/*<Link*/}
          {/*  component="button"*/}
          {/*  type="button"*/}
          {/*  onClick={handleClickOpen}*/}
          {/*  variant="body2"*/}
          {/*  sx={{ alignSelf: 'center' }}*/}
          {/*>*/}
          {/*  Forgot your password?*/}
          {/*</Link>*/}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>Cancel</Button>

        <Button onClick={() => {
          if (formRef.current) {
            formRef.current.requestSubmit()
          }
        }} variant="contained">
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}
