import React from "react";
import {Form} from "semantic-ui-react";
import BaseForm from "./BaseForm";
import {checkForErrors, isNotEmpty, isAnInteger, isAPositiveInteger, isLargerThan, isAPositiveNumber} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";
import { mergeUnlessNull } from "../../Utils/utilMethods";

class SamplerForm extends React.Component {
    constructor(props) {
        super(props);

        this.initialData = mergeUnlessNull(
            {
                samplerChoice: 'dynesty',
                nlive: '1000',
                nact: '10',
                maxmcmc: '5000',
                walks: '1000',
                dlogz: '0.1',
                cpus: '1'
            },
            this.props.data,
            this.props.state
        )
    }

    setForms = (values) => {
        const forms = [
            {
                label: 'Sampler',
                name: 'samplerChoice',
                form: <Form.Select placeholder="Select Sampler" options={[
                    {key: 'dynesty', text: 'Dynesty', value: 'dynesty'},
                ]}/>
            },

            {
                label: 'Number of live points',
                name: 'nlive',
                form: <Form.Input placeholder="1000" />,
                errFunc: checkForErrors(isLargerThan(100), isAnInteger, isNotEmpty)
            },

            {
                label: 'Number of auto-correlation steps',
                name: 'nact',
                form: <Form.Input placeholder="10" />,
                errFunc: checkForErrors(isAPositiveInteger, isNotEmpty)
            },

            {
                label: 'Maximum number of steps',
                name: 'maxmcmc',
                form: <Form.Input placeholder="5000" />,
                errFunc: checkForErrors(isAPositiveInteger, isNotEmpty)
            },

            {
                label: 'Minimum number of walks',
                name: 'walks',
                form: <Form.Input placeholder="1000" />,
                errFunc: checkForErrors(isAPositiveInteger, isNotEmpty)
            },

            {
                label: 'Stopping criteria',
                name: 'dlogz',
                form: <Form.Input placeholder="0.1" />,
                errFunc: checkForErrors(isAPositiveNumber, isNotEmpty)
            },
            
            {
                label: 'Number of CPUs to use for parallelisation',
                name: 'cpus',
                form: <Form.Input placeholder="1" disabled/>,
                errFunc: checkForErrors(isAPositiveInteger, isNotEmpty)
            },
        ]
        
        return forms
    }

    render() {
        return (
            <BaseForm
                initialData={this.initialData}
                setForms={this.setForms}
                prevStep={this.props.prevStep}
                nextStep={this.props.nextStep}
                updateParentState={this.props.updateParentState}
            />
        )
    }
}

export default createFragmentContainer(SamplerForm, {
    data: graphql`
        fragment SamplerForm_data on SamplerType {
            samplerChoice
            nlive
            nact
            maxmcmc
            walks
            dlogz
            cpus
        }
    `
});