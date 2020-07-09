import React from "react";
import {Form} from "semantic-ui-react";
import BaseForm from "./BaseForm";

import { graphql, createFragmentContainer } from "react-relay";

class SamplerForm extends React.Component {
    constructor(props) {
        super(props);

        this.initialData = {
            samplerChoice: 'dynesty',
        }

        this.initialData = (this.props.data !== null) ? this.props.data : this.initialData
        this.initialData = (this.props.state !== null) ? this.props.state : this.initialData
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
            number
        }
    `
});