import React from 'react';
import { MockPayloadGenerator } from 'relay-test-utils';
import { QueryRenderer, graphql } from 'react-relay';
import { render, fireEvent } from '@testing-library/react';
import PrivacyToggle from '../PrivacyToggle';

/* global environment, router */

describe('the privacy toggle component', () => {

    const TestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
            query PrivacyToggleTestQuery ($jobId: ID!)
              @relay_test_operation {
                bilbyJob(id: $jobId) {
                  ...PrivacyToggle_data
               }
             }
          `}
            variables={{
                jobId: '1234' 
            }}
            render={({ error, props }) => {
                if (props) {
                    return <PrivacyToggle
                        data={props.bilbyJob}
                        match={{}}
                        router={router}
                        onUpdate={()=>{}}
                        modifiable
                    />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockReturnLigo = {
        BilbyJobNode() {
            return {
                private: true,
                isLigoJob: true
            };
        }
    };

    const mockReturnNonLigo = {
        BilbyJobNode() {
            return {
                private: true,
                isLigoJob: false
            };
        }
    };

    it('should render the privacy toggle with correct query data (LIGO)', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockReturnLigo)
        );
        expect(getByLabelText('Share with LVK collaborators')).not.toBeChecked();
    });

    it('should toggle the checked value on click (LIGO)', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockReturnLigo)
        );
        const privacyCheck = getByLabelText('Share with LVK collaborators');
        expect(privacyCheck).not.toBeChecked();
        fireEvent.click(privacyCheck);
        expect(privacyCheck).toBeChecked();
    });

    it('should send a mutation when clicked (LIGO)', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockReturnLigo)
        );
        const privacyCheck = getByLabelText('Share with LVK collaborators');
        fireEvent.click(privacyCheck);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation)
        );
        expect(privacyCheck).toBeChecked();
    });

    it('should render the privacy toggle with correct query data (Not LIGO)', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockReturnNonLigo)
        );
        expect(getByLabelText('Share publicly')).not.toBeChecked();
    });

    it('should toggle the checked value on click (Not LIGO)', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockReturnNonLigo)
        );
        const privacyCheck = getByLabelText('Share publicly');
        expect(privacyCheck).not.toBeChecked();
        fireEvent.click(privacyCheck);
        expect(privacyCheck).toBeChecked();
    });

    it('should send a mutation when clicked (Not LIGO)', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockReturnNonLigo)
        );
        const privacyCheck = getByLabelText('Share publicly');
        fireEvent.click(privacyCheck);
        environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation)
        );
        expect(privacyCheck).toBeChecked();
    });
});
