import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import EditableDescription from '../EditableDescription';
import userEvent from '@testing-library/user-event';
import { MockPayloadGenerator } from 'relay-test-utils';

/* global environment */

describe('editable description component', () => {
    it('should render', () => {
        expect.hasAssertions();
        render(<EditableDescription value="Testing" />);
        expect(screen.getByText('Testing')).toBeInTheDocument();
    });

    it('should call a mutation when changed', async () => {
        expect.hasAssertions();
        const { container } = render(<EditableDescription modifiable={true} value="Testing" jobId={1} />);
        userEvent.click(screen.getByText('edit'));
        userEvent.type(screen.getByDisplayValue('Testing'), '-new-value');
        await waitFor(() => userEvent.click(container.getElementsByClassName('save-button')[0]));
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) => MockPayloadGenerator.generate(operation)),
        );
        expect(screen.getByText('Testing-new-value')).toBeInTheDocument();
    });
});
