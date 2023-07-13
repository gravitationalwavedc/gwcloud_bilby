import React from 'react';
import { MockPayloadGenerator } from 'relay-test-utils';
import { QueryRenderer, graphql } from 'react-relay';
import { render, fireEvent } from '@testing-library/react';
import PublicJobs from '../PublicJobs';

/* global environment, router */

describe('public Job Page', () => {
    const TestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query PublicJobsTestQuery($count: Int, $timeRange: String, $cursor: String, $search: String)
                @relay_test_operation {
                    ...PublicJobs_data
                }
            `}
            variables={{
                count: 10,
                timeRange: 'all',
            }}
            render={({ error, props }) => {
                if (props) {
                    return <PublicJobs data={props} match={{}} router={router} />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockReturn = {
        BilbyPublicJobNode() {
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

    it('renders', () => {
        expect.hasAssertions();
        const { getByText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        expect(getByText('Public Jobs')).toBeInTheDocument();
    });

    it('calls refetchConnection when the serach field is updated', () => {
        expect.hasAssertions();
        const { getByLabelText, getByText, queryByText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        // When the page first loads it should match the initial mock query
        expect(getByText(/Buffy/)).toBeInTheDocument();

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
                BilbyPublicJobNode() {
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
        expect(getByText(/Giles/)).toBeInTheDocument();
        expect(queryByText(/Buffy/)).not.toBeInTheDocument();
    });

    it('calls refetchConnection when the time range is changed', () => {
        expect.hasAssertions();
        const { getByLabelText, getByText, queryByText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        // When the page first loads it should match the initial mock query
        expect(getByText(/Buffy/)).toBeInTheDocument();

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
                BilbyPublicJobNode() {
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
        expect(getByText(/Giles/)).toBeInTheDocument();
        expect(queryByText(/Buffy/)).not.toBeInTheDocument();
    });
});
