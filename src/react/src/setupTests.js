import React from 'react';
import { render } from '@testing-library/react';
import { createMockEnvironment } from 'relay-test-utils';
import { QueryRenderer } from 'react-relay';

// Global imports for tests
// import '@testing-library/jest-dom/extend-expect';
import '@testing-library/jest-dom';

const environment = createMockEnvironment();


// global.queryRendererSetup = (inputQuery, componentToRender) => {
//   render(
//     <QueryRenderer
//       environment={environment}
//       query={inputQuery}
//       variables={{}}
//       render={({ error, props }) => {
//         if (props) {
//           return componentToRender(props);
//         } else if (error) {
//           return error.message;
//         }
//         return 'Loading...';
//       }}
//     />,
//   );
//   return environment;
// };

global.router = {
  push: jest.fn(),
  replace: jest.fn(),
  go: jest.fn(),
  createHref: jest.fn(),
  createLocation: jest.fn(),
  isActive: jest.fn(),
  matcher: {
    match: jest.fn(),
    getRoutes: jest.fn(),
    isActive: jest.fn(),
    format: jest.fn(),
  },
  addTransitionHook: jest.fn(),
  addNavigationListener: jest.fn(),
};

global.environment = environment;
