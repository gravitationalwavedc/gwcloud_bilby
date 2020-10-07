
import React from 'react';
import { QueryRenderer, graphql } from 'react-relay';
import { render } from '@testing-library/react';
import ViewJob from '../ViewJob';

describe('New Job Page', () => {
  const TestRenderer = () => (
      <QueryRenderer
          environment={environment}
          query={graphql`
            query ViewJobTestQuery($jobId: ID!)  @relay_test_operation {
              ...ViewJob_data @arguments(jobId: $jobId)
            }
          `}
          variables={{
            jobId: '1234'
          }}
          render={({ error, props }) => {
              if (props) {
                return <ViewJob data={props} match={{}} router={router}/>;
              } else if (error) {
                  return error.message;
              }
              return 'Loading...';
          }}
      />
  );

  it('renders', () => {
    render(<TestRenderer />);
  });
});
