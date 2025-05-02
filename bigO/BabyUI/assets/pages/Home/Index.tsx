import * as React from 'react';
import * as Material from '@mui/material';
import { Head } from '@inertiajs/react';

interface Propps {
  title: string;
}

const Index = ({ title }: Propps): React.ReactNode => {
  let [count, setCount] = React.useState(0);
  return (
    <>
      <Head title="Title" />
      <div>
        <Material.Typography>this is {title}</Material.Typography>
        <Material.Button onClick={() => setCount(count + 1)}>
          count is: {count}
        </Material.Button>
      </div>
    </>
  );
};

export default Index;
