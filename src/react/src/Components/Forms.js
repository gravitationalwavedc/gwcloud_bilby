import React from "react";
import {Form, Divider, Grid, Label} from "semantic-ui-react";
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
import {assembleErrorString} from "../Utils/errors";



function BaseForm({forms, validate, onChange}) {
    const form_arr = forms.map((form, index) => <FormRow key={index} rowName={form.rowName} children={form.form} errors={form.errors} validate={validate} onChange={onChange}/>)

    return (
        <Grid.Row>
            <Grid.Column width={8}>
                <Grid divided='vertically' textAlign='left'>
                    {form_arr}
                </Grid>
            </Grid.Column>
        </Grid.Row>

    )
}

class PriorsFormInput extends React.Component {
    constructor(props) {
        super(props);

        this.state = this.props.value
    }
    
    handleChange = (e, data) => {
        const newState = {
            ...this.state,
            [data.name]: data.value
        }
        this.setState(newState)
        this.props.onChange(this.props.name, newState)
    }

    render() {
        return (
            <Grid textAlign='left'>
                <Grid.Column width={16}>
                    <Divider horizontal>{this.props.title}</Divider>
                </Grid.Column>
                <Grid.Row columns={4}>
                    <Grid.Column>
                        Type
                    </Grid.Column>
                    <Grid.Column>
                        <Form.Select name={'type'} value={this.state.type} onChange={this.handleChange} options={[
                            {key: 'fixed', text: 'Fixed', value: 'fixed'},
                            {key: 'uniform', text: 'Uniform', value: 'uniform'},
                        ]}/>
                    </Grid.Column>
                </Grid.Row>
                {this.state.type === 'fixed' ? 
                    <Grid.Row columns={4}>
                        <Grid.Column>
                            Value
                        </Grid.Column>
                        <Grid.Column>
                            <Form.Input fluid name='value' placeholder='Hello' value={this.state.value} onChange={this.handleChange} error={this.props.error}/>
                        </Grid.Column>
                    </Grid.Row>
                :
                    <Grid.Row columns={4}>
                        <Grid.Column children='Min'/>
                        <Grid.Column>
                            <Form.Input fluid name='min' placeholder='Hello' value={this.state.min} onChange={this.handleChange} error={this.props.error}/>
                        </Grid.Column>
                        <Grid.Column children='Max'/>
                        <Grid.Column>
                            <Form.Input fluid name='max' placeholder='Hello' value={this.state.max} onChange={this.handleChange} error={this.props.error}/>
                        </Grid.Column>
                    </Grid.Row>
                }
            </Grid>
        )
    }
}

function FormRow(props) {
    let formHasError = false
    if (props.errors && props.errors.length && props.validate) {
        formHasError = true
    }
    return (
        <Grid.Row columns={3}>
            <Grid.Column verticalAlign='middle' width={4}>
                {props.rowName}
            </Grid.Column>
            <Grid.Column verticalAlign='middle' width={8}>
                <Form>
                    {React.Children.map(props.children, (child => React.cloneElement(child, {onChange: props.onChange, error: formHasError})))}
                </Form>
            </Grid.Column>
            <Grid.Column verticalAlign='middle' width={4}>
                {formHasError ? <Label basic pointing='left' color='red' content={assembleErrorString(props.errors)}/> : null}
            </Grid.Column>
        </Grid.Row>
    )

}

export {
    BaseForm,
    PriorsFormInput
};