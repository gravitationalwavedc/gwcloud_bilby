import React from 'react';
import { MockPayloadGenerator } from 'relay-test-utils';
import { QueryRenderer, graphql } from 'react-relay';
import { render } from '@testing-library/react';
import DuplicateJobForm from '../Forms/DuplicateJobForm';

/* global environment, router */

describe('duplicate a job and create a new form', () => {
    const TestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query DuplicateJobFormTestQuery($jobId: ID!) @relay_test_operation {
                    ...DuplicateJobForm_data @arguments(jobId: $jobId)
                }
            `}
            variables={{
                jobId: '1234',
            }}
            render={({ error, props }) => {
                if (props) {
                    return <DuplicateJobForm data={props} match={{}} router={router} />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockReturn = {
        BilbyJobNode() {
            return {
                params: {
                    details: {
                        name: 'TestJob-1',
                        description: 'A test job.',
                    },
                },
            };
        },
    };

    it('renders with copy of returned data', () => {
        expect.hasAssertions();
        const { getByText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn)
        );
        expect(getByText('Copy-of-TestJob-1')).toBeInTheDocument();
        expect(
            getByText('A duplicate job of Copy-of-TestJob-1. Original description: A test job.')
        ).toBeInTheDocument();
    });
});
