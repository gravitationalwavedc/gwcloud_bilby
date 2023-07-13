import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import EditableJobName from '../EditableJobName';
import userEvent from '@testing-library/user-event';
import { MockPayloadGenerator } from 'relay-test-utils';

/* global environment */

describe('editable job name component', () => {
    it('should render', () => {
        expect.hasAssertions();
        render(<EditableJobName value="Testing" />);
        expect(screen.getByText('Testing')).toBeInTheDocument();
    });

    it('should call a mutation when changed', async () => {
        expect.hasAssertions();
        const { container } = render(<EditableJobName modifiable={true} value="Testing" jobId={1} />);
        userEvent.click(screen.getByText('edit'));
        userEvent.type(screen.getByDisplayValue('Testing'), '-new-value');
        await waitFor(() => userEvent.click(container.getElementsByClassName('save-button')[0]));
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) => MockPayloadGenerator.generate(operation)),
        );
        expect(screen.getByText('Testing-new-value')).toBeInTheDocument();
    });

    it('should display errors correctly', async () => {
        expect.hasAssertions();
        const { container } = render(<EditableJobName modifiable={true} value="Testing" jobId={1} />);
        userEvent.click(screen.getByText('edit'));
        userEvent.type(screen.getByDisplayValue('Testing'), ' bad v@!u3');
        await waitFor(() => userEvent.click(container.getElementsByClassName('save-button')[0]));
        expect(screen.getByText('Remove any spaces or special characters.')).toBeInTheDocument();
    });

    it('should display graphql mutation errors correctly', async () => {
        expect.hasAssertions();
        const { container } = render(<EditableJobName modifiable={true} value="Testing" jobId={1} />);
        userEvent.click(screen.getByText('edit'));
        userEvent.type(screen.getByDisplayValue('Testing'), '-bad-graphql-mutation');
        await waitFor(() => userEvent.click(container.getElementsByClassName('save-button')[0]));
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation(() => ({
                data: { updateBilbyJob: { jobId: null, result: null } },
                errors: [{ message: 'Duplicate job name found! Bad!' }, { message: 'So bad. Do a stop!' }],
            })),
        );
        expect(screen.getByText(/Duplicate job name found! Bad!/)).toBeInTheDocument();
        expect(screen.getByText(/So bad. Do a stop!/)).toBeInTheDocument();
    });

    it('should clear errors when the mutation is successful', async () => {
        expect.hasAssertions();
        const { container } = render(<EditableJobName modifiable={true} value="Testing" jobId={1} />);
        userEvent.click(screen.getByText('edit'));
        userEvent.type(screen.getByDisplayValue('Testing'), '-bad-graphql-mutation');
        await waitFor(() => userEvent.click(container.getElementsByClassName('save-button')[0]));
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation(() => ({
                data: { updateBilbyJob: { jobId: null, result: null } },
                errors: [{ message: 'Duplicate job name found! Bad!' }, { message: 'So bad. Do a stop!' }],
            })),
        );
        expect(screen.getByText(/Duplicate job name found! Bad!/)).toBeInTheDocument();
        expect(screen.getByText(/So bad. Do a stop!/)).toBeInTheDocument();

        userEvent.click(screen.getByText('edit'));
        const nameInput = screen.getByDisplayValue('Testing-bad-graphql-mutation');
        userEvent.clear(nameInput);
        userEvent.type(nameInput, 'Good-name');
        await waitFor(() => userEvent.click(container.getElementsByClassName('save-button')[0]));
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) => MockPayloadGenerator.generate(operation)),
        );
        expect(screen.queryByText(/Duplicate job name found! Bad!/)).not.toBeInTheDocument();
        expect(screen.queryByText(/So bad. Do a stop!/)).not.toBeInTheDocument();
    });
});
