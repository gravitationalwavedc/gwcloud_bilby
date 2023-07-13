import React from 'react';
import LabelDropdown from '../LabelDropdown';
import { graphql, QueryRenderer } from 'react-relay';
import { MockPayloadGenerator } from 'relay-test-utils';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

/* global environment */

describe('the label dropdown component', () => {
    const onUpdateMock = jest.fn();

    const TestRenderer = ({ modifiable }) => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query LabelDropdownTestQuery($jobId: ID!) @relay_test_operation {
                    ...LabelDropdown_data @arguments(jobId: $jobId)
                }
            `}
            variables={{
                jobId: 'QmlsYnlKb2JOb2RlOjY=',
            }}
            render={({ error, props }) => {
                if (props) {
                    return <LabelDropdown data={props} modifiable={modifiable} onUpdate={onUpdateMock} />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockLabelData = {
        BilbyJobNode() {
            return {
                labels: [
                    {
                        name: 'test-label',
                    },
                ],
            };
        },
        AllLabelsConnection() {
            return {
                edges: [
                    {
                        node: {
                            name: 'test-label',
                            description: 'a label',
                            protected: false,
                        },
                    },
                    {
                        node: {
                            name: 'test-label-2',
                            description: 'a label two',
                            protected: false,
                        },
                    },
                ],
            };
        },
    };

    it('should render', () => {
        expect.hasAssertions();
        render(<TestRenderer />);
        expect(screen.queryByText('Loading...')).toBeInTheDocument();
    });

    it('should render and load relay data', async () => {
        expect.hasAssertions();
        render(<TestRenderer />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockLabelData)
            )
        );
        expect(screen.queryByText('test-label')).toBeInTheDocument();
        expect(screen.queryByTestId('dismissable-link')).not.toBeInTheDocument();
        expect(screen.queryByText('Add label')).not.toBeInTheDocument();
    });

    it('should render as modifiable', async () => {
        expect.hasAssertions();
        render(<TestRenderer modifiable={true} />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockLabelData)
            )
        );
        expect(screen.getByTestId('dismissable-link')).toBeInTheDocument();
        expect(screen.queryByText('Add label')).toBeInTheDocument();
    });

    it('should update the list of labels', async () => {
        expect.hasAssertions();
        render(<TestRenderer modifiable={true} />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockLabelData)
            )
        );
        const addLabelButton = screen.queryByText('Add label');
        await waitFor(() => userEvent.click(addLabelButton));
        expect(await screen.findByText('test-label-2')).toBeInTheDocument();
        const addLabelLink = screen.queryByText('test-label-2');
        await waitFor(() => userEvent.click(addLabelLink));
        expect(await screen.findByText('test-label-2')).toBeInTheDocument();
    });

    it('should have dismissable labels', async () => {
        expect.hasAssertions();
        render(<TestRenderer modifiable={true} />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockLabelData)
            )
        );
        expect(screen.queryByText('test-label')).toBeInTheDocument();
        const dismissableLink = screen.queryByTestId('dismissable-link');
        await waitFor(() => userEvent.click(dismissableLink));
        expect(screen.queryByText('test-label')).not.toBeInTheDocument();
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) => MockPayloadGenerator.generate(operation))
        );
        expect(onUpdateMock).toHaveBeenCalledWith(true, 'Job labels updated!');
        onUpdateMock.mockRestore();
    });

    it('should display errors from the api', async () => {
        expect.hasAssertions();
        render(<TestRenderer modifiable={true} />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockLabelData)
            )
        );
        expect(screen.queryByText('test-label')).toBeInTheDocument();
        const dismissableLink = screen.queryByTestId('dismissable-link');
        await waitFor(() => userEvent.click(dismissableLink));
        expect(screen.queryByText('test-label')).not.toBeInTheDocument();
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation(() => ({
                errors: [{ message: 'Label updated failed' }],
                data: { updateBilbyJob: { result: false } },
            }))
        );
        expect(onUpdateMock).toHaveBeenCalledWith(false, [{ message: 'Label updated failed' }]);
        onUpdateMock.mockRestore();
    });
});
