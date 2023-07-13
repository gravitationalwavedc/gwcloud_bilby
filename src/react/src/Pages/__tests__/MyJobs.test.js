import React from 'react';
import { MockPayloadGenerator } from 'relay-test-utils';
import { QueryRenderer, graphql } from 'react-relay';
import { render, fireEvent } from '@testing-library/react';
import MyJobs from '../MyJobs';

/* global environment, router */

describe('my Jobs Page', () => {
    const TestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query MyJobsTestQuery($count: Int, $cursor: String, $orderBy: String) @relay_test_operation {
                    ...MyJobs_data
                }
            `}
            variables={{
                count: 10,
                orderBy: 'Name',
            }}
            render={({ error, props }) => {
                if (props) {
                    return <MyJobs data={props} match={{}} router={router} />;
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
                id: '1',
                user: 'Buffy',
                labels: [],
                jobStatus: { name: 'complete' },
                name: 'TestJob-1',
                description: 'A test job',
                timestamp: 'timestamp',
            };
        },
    };

    it('renders with data', () => {
        expect.hasAssertions();
        const { getByText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        expect(getByText('My Jobs')).toBeInTheDocument();
    });

    it('calls refetchConnection when the serach field is updated', () => {
        expect.hasAssertions();
        const { getByLabelText, getByText, queryByText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        // When the page first loads it should match the initial mock query
        expect(getByText('TestJob-1')).toBeInTheDocument();

        // Simulate searching
        const searchField = getByLabelText('Search');
        fireEvent.change(searchField, { target: { value: 'Giles' } });

        // Refetch the container
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, {
                PageInfo() {
                    return {
                        hasNextPage: true,
                        endCursor: 'endcursor',
                    };
                },
                BilbyJobNode() {
                    return {
                        id: '2',
                        user: 'Giles',
                        labels: [],
                        jobStatus: { name: 'complete' },
                        name: 'TestJob-2',
                        description: 'A load more job.',
                        timestamp: 'timestamp',
                    };
                },
            }),
        );

        // Check the table updated.
        expect(getByText('TestJob-2')).toBeInTheDocument();
        expect(queryByText('TestJob-1')).not.toBeInTheDocument();
    });

    it('calls refetchConnection when the time range is changed', () => {
        expect.hasAssertions();
        const { getByLabelText, getByText, queryByText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        // When the page first loads it should match the initial mock query
        expect(getByText('TestJob-1')).toBeInTheDocument();

        // Simulate changing the time field
        const timeRangeField = getByLabelText('Time');
        fireEvent.change(timeRangeField, { target: { value: '1d' } });

        // Refetch the container
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, {
                PageInfo() {
                    return {
                        hasNextPage: true,
                        endCursor: 'endcursor',
                    };
                },
                BilbyJobNode() {
                    return {
                        id: '2',
                        user: 'Giles',
                        labels: [],
                        jobStatus: { name: 'complete' },
                        name: 'TestJob-2',
                        description: 'A load more job.',
                        timestamp: 'timestamp',
                    };
                },
            }),
        );

        // Check the table updated.
        expect(getByText('TestJob-2')).toBeInTheDocument();
        expect(queryByText('TestJob-1')).not.toBeInTheDocument();
    });
});
