import React from 'react';
import { MockPayloadGenerator } from 'relay-test-utils';
import { render, fireEvent, waitFor } from '@testing-library/react';
import NewJob from '../NewJob';

describe('New Job Page', () => {
  it('renders', () => {
    render(<NewJob />);
  });

  it('should send a mutation when the form is submitted', async () => {
    const { getByText } = render(<NewJob router={router} />);
    const submitButton = getByText('Submit your job');
    fireEvent.click(submitButton);
    let operation;
    await waitFor(() => {operation = environment.mock.getMostRecentOperation()});
    environment.mock.resolve(
      operation,
      MockPayloadGenerator.generate(operation)
    );
    expect(router.replace).toBeCalled();
  });

  it('should navigate between tabs', () => {
    const {  getByTestId, getByText } = render(<NewJob />);
    const signalPane = getByTestId('signalPane');
    expect(signalPane).toHaveAttribute('aria-hidden', 'true');
    const signalNavButton = getByText('Injection type and details');
    fireEvent.click(signalNavButton);
    expect(signalPane).toHaveAttribute('aria-hidden', 'false');
  });
});

