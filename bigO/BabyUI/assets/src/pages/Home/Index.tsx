import * as React from 'react';

const Index = (): React.ReactNode => {
    let [count, setCount] = React.useState(0)
  return (
    <div>
      <button onClick={() => setCount(count + 1)}>count is: {count}</button>
    </div>
  )
}

export default Index;
