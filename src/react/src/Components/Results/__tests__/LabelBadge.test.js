import React from 'react';
import LabelBadge from '../LabelBadge';
import { render, screen } from '@testing-library/react';

describe('label badge component', () => {

    it('should render without being dismissable', () => {
        expect.hasAssertions();
        render(<LabelBadge name="test" />);
        expect(screen.queryByText('test')).toBeInTheDocument();
        expect(screen.queryByTestId('dismissable-link')).not.toBeInTheDocument();
    });

    it('should render with modifiable buttons', () => {
        expect.hasAssertions();
        render(<LabelBadge name="test" dismissable={true} />);
        expect(screen.queryByText('test')).toBeInTheDocument();
        expect(screen.queryByTestId('dismissable-link')).toBeInTheDocument();
    });
});
