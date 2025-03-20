import * as React from 'react';
import * as Material from '@mui/material';

interface Propps {
  title: string;
}
const Index = ({ title }: Propps): React.ReactNode => {
  console.log(title);
  let [count, setCount] = React.useState(0);
  return (
    <div>
      <Material.Typography>this is {title}</Material.Typography>
      <Material.Button onClick={() => setCount(count + 1)}>
        count is: {count}
      </Material.Button>
    </div>
  );
};

export default Index;
