import React from 'react';
import { MockPayloadGenerator } from 'relay-test-utils';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import NewJob from '../NewJob';
import { graphql, QueryRenderer } from 'react-relay';
import userEvent from '@testing-library/user-event';

/* global router, environment */

describe('new Job Page', () => {
    const TestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query NewJobTestQuery @relay_test_operation {
                    ...DataForm_data
                }
            `}
            render={({ error, props }) => {
                if (props) {
                    return <NewJob data={props} match={{}} router={router} />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockReturn = {
        EventIDType() {
            return {
                eventId: 'test-1',
                triggerId: 'trigger-1',
                nickname: 'slayer',
            };
        },
    };

    it('should send a mutation when the form is submitted', async () => {
        expect.hasAssertions();
        const { getByText, getByTestId } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        fireEvent.click(getByTestId('hanfordActive'));
        fireEvent.click(getByText('Submit your job'));
        const operation = await waitFor(() => environment.mock.getMostRecentOperation());
        environment.mock.resolve(operation, MockPayloadGenerator.generate(operation));
        expect(router.replace).toHaveBeenCalledWith('/bilby/job-results/<mock-value-for-field-"jobId">/');
    });

    it('should navigate between tabs', () => {
        expect.hasAssertions();
        const { getByText, getByTestId } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation((operation) =>
            MockPayloadGenerator.generate(operation, mockReturn),
        );
        const signalPane = getByTestId('signalPane');
        expect(signalPane).toHaveAttribute('aria-hidden', 'true');
        const signalNavButton = getByText('Injection type and details');
        fireEvent.click(signalNavButton);
        expect(signalPane).toHaveAttribute('aria-hidden', 'false');
    });

    it('should change event id when using the Event ID modal', async () => {
        expect.hasAssertions();
        render(<TestRenderer />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockReturn),
            ),
        );

        expect(screen.queryByText('Event ID: test-1')).not.toBeInTheDocument();

        const changeEventIdBtn = screen.getByText('Set Event ID');
        userEvent.click(changeEventIdBtn);
        const modalInput = screen.getByRole('combobox');
        userEvent.click(modalInput);
        const idSelection = screen.getByLabelText('test-1');
        userEvent.click(idSelection);
        expect(screen.queryByText('Event ID: test-1')).toBeInTheDocument();
        expect(screen.queryByText('Change Event ID')).toBeInTheDocument();
    });
});
