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
                    return <PrivacyToggle data={props.bilbyJob} match={{}} router={router} onUpdate={()=>{}} modifiable/>;
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
                private: true
            };
        }
    };

    it('should render the privacy toggle with correct query data', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation => 
            MockPayloadGenerator.generate(operation, mockReturn)
        );
        expect(getByLabelText('Share with LIGO collaborators')).not.toBeChecked();
    });

    it('should toggle the checked value on click', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation => 
            MockPayloadGenerator.generate(operation, mockReturn)
        );
        const privacyCheck = getByLabelText('Share with LIGO collaborators');
        expect(privacyCheck).not.toBeChecked();
        fireEvent.click(privacyCheck);
        expect(privacyCheck).toBeChecked();
    });

    it('should send a mutation when clicked', () => {
        expect.hasAssertions();
        const { getByLabelText } = render(<TestRenderer />);
        environment.mock.resolveMostRecentOperation(operation => 
            MockPayloadGenerator.generate(operation, mockReturn)
        );
        const privacyCheck = getByLabelText('Share with LIGO collaborators');
        fireEvent.click(privacyCheck);
        environment.mock.resolveMostRecentOperation(operation => 
            MockPayloadGenerator.generate(operation)
        );
        expect(privacyCheck).toBeChecked();
    });
});
