import { router, usePage } from '@inertiajs/react';
import {
  Typography,
  Box,
  FormControl,
  TextField,
  FormHelperText,
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
  CircularProgress,
} from '@mui/material';
import * as React from 'react';
import { PlanProvider, PlanRecord } from '../services/types.ts';
interface Props {
  isOpen: boolean;
  setOpen: (isOpen: boolean) => void;
  plans: PlanRecord[];
}

export default function UserDialogForm({ isOpen, setOpen, plans }: Props) {
  let {
    url,
    props: { errors },
  } = usePage();
  let [isSubmitting, setIsSubmitting] = React.useState(false);
  errors = errors || {};
  let titleErrorMessage = errors.title;
  let descriptionErrorMessage = errors.description;
  let planErrorMessage = errors.plan;
  let expiryDaysErrorMessage = errors.expiry_days;
  let VolumeGBErrorMessage = errors.volume_gb;
  // let ErrorMessage = errors.plan;
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    const data = new FormData(event.currentTarget);
    data.append('action', 'new_user');
    console.log(data);
    const dataf = Object.fromEntries(data.entries());
    console.log(dataf);
    router.post(url, data, {
      onSuccess: () => setOpen(false),
      onFinish: () => setIsSubmitting(false),
    });
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
              error={!!expiryDaysErrorMessage}
              helperText={expiryDaysErrorMessage}
              name="newuser1-expiry_days"
              type="number"
              label="Expiry"
              id="newuser1-expiry_days"
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
              color={expiryDaysErrorMessage ? 'error' : 'primary'}
            />
          </FormControl>
          <FormControl>
            <TextField
              error={!!VolumeGBErrorMessage}
              helperText={VolumeGBErrorMessage}
              label={'Volume'}
              name="newuser1-volume_gb"
              type="number"
              id="newuser1-volume_gb"
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
              color={VolumeGBErrorMessage ? 'error' : 'primary'}
            />
          </FormControl>
        </>
      );
    }
  }
  const formRef = React.useRef(null);
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
            action button for that user
          </Typography>

          <Typography color="error" sx={{ mt: 1 }}>
            {errors.__all__}
          </Typography>

          <FormControl>
            <TextField
              error={!!titleErrorMessage}
              helperText={titleErrorMessage}
              name="newuser1-title"
              label="Title"
              id="newuser1-title"
              required
              fullWidth
              variant="outlined"
              color={titleErrorMessage ? 'error' : 'primary'}
            />
          </FormControl>
          <FormControl>
            <TextField
              multiline
              error={!!descriptionErrorMessage}
              helperText={descriptionErrorMessage}
              name="newuser1-description"
              label="Description"
              id="newuser1-description"
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
              name="newuser1-plan"
              id="newuser1-plan"
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
                  return <em>Not Available</em>;
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
            {planErrorMessage && (
              <FormHelperText error={true}>
                Here's my helper text
              </FormHelperText>
            )}
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

        <Button
          onClick={() => {
            if (formRef.current) {
              formRef.current.requestSubmit();
            }
          }}
          variant="contained"
        >
          {isSubmitting ? <CircularProgress /> : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
