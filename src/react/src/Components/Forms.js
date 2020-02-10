import React from "react";
import {Form} from "semantic-ui-react";

class BaseForm extends React.Component {

    render() {
        // const {values} = this.props

        return(
            <div>
                {this.props.children}
            </div>
        )
    }
}

const StartForm = ({handleChange}) => 
    <Form>
        <Form.Input label="Job Name" placeholder="Job Name" onChange={handleChange}/>
    </Form>

const DataForm = () => 
    <BaseForm>
        Forms go here        
    </BaseForm>

const SignalForm = () => 
    <BaseForm>
        Forms go here        
    </BaseForm>

const PriorsForm = () => 
    <BaseForm>
        Forms go here        
    </BaseForm>

const SamplerForm = () => 
    <BaseForm>
        Forms go here        
    </BaseForm>

const SubmitForm = () => 
    <BaseForm>
        Forms go here        
    </BaseForm>

export {
    StartForm,
    DataForm,
    SignalForm,
    PriorsForm,
    SamplerForm,
    SubmitForm
};