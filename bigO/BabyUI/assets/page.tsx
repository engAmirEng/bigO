import { createRoot } from 'react-dom/client';
import { createInertiaApp } from '@inertiajs/react';
import CssBaseline from '@mui/material/CssBaseline';
import axios from 'axios';

axios.defaults.xsrfHeaderName = 'X-CSRFToken';
axios.defaults.xsrfCookieName = 'csrftoken';
document.addEventListener('DOMContentLoaded', () => {
  createInertiaApp({
    resolve: (name) => {
      const pages = import.meta.glob('./pages/**/*.tsx', { eager: true });
      return pages[`./pages/${name}.tsx`];
    },
    setup({ el, App, props }) {
      createRoot(el).render(
        <>
          <CssBaseline />
          <App {...props} />
        </>
      );
    },
  }).then(() => {});
});
