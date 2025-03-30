import { styled } from '@mui/material/styles';
import Typography from '@mui/material/Typography';
import Breadcrumbs, { breadcrumbsClasses } from '@mui/material/Breadcrumbs';
import NavigateNextRoundedIcon from '@mui/icons-material/NavigateNextRounded';
import type {} from '@mui/material/themeCssVarsAugmentation';

const StyledBreadcrumbs = styled(Breadcrumbs)(({ theme }) => ({
  margin: theme.spacing(1, 0),
  [`& .${breadcrumbsClasses.separator}`]: {
    color: (theme.vars || theme).palette.action.disabled,
    margin: 1,
  },
  [`& .${breadcrumbsClasses.ol}`]: {
    alignItems: 'center',
  },
}));

interface Props {
  levels: string[];
}
export default function NavbarBreadcrumbs({ levels }: Props) {
  return (
    <StyledBreadcrumbs
      aria-label="breadcrumb"
      separator={<NavigateNextRoundedIcon fontSize="small" />}
    >
      {levels.map((value, index) => (
        <Typography key={index} variant="body1">
          {value}
        </Typography>
      ))}

      {/*<Typography variant="body1" sx={{ color: 'text.primary', fontWeight: 600 }}>*/}
      {/*  Home*/}
      {/*</Typography>*/}
    </StyledBreadcrumbs>
  );
}
