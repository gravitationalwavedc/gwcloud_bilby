import React from "react";
import {Form, Divider, Grid, Label} from "semantic-ui-react";
import {assembleErrorString} from "../../Utils/errors";



function BaseForm({data, errors, forms, onChange, validate}) {
    const form_arr = forms.map(({label, name, form, errFunc, requiredField, toggle}, index) => (toggle ? null : <FormBundle key={index} label={label} children={form} name={name} value={data[name]} errors={errors[name]} errFunc={errFunc} validate={validate} onChange={onChange} required={typeof(requiredField) !== 'undefined' ? requiredField : true}/>))

    return (
        <Grid.Row>
            <Grid.Column width={10}>
                <Form>
                    <Grid textAlign='left'>
                        {form_arr}
                    </Grid>
                </Form>
            </Grid.Column>
        </Grid.Row>

    )
}

class PriorsFormInput extends React.Component {
    constructor(props) {
        super(props);

        var initialState = {}
        for (let [key, val] of Object.entries(this.props.value)) {
            initialState[key] = val !== null ? val : ''
        }
        this.state = initialState
    }
    
    handleChange = (e, data) => {
        const newState = {
            ...this.state,
            [data.name]: data.value
        }
        this.setState(newState)
        this.props.onChange(e, {name: this.props.name, value: newState})
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

// Changed to a class component to allow checking errors on the initial values
// Can be changed back with react hooks
class FormBundle extends React.Component {

    componentDidMount() {
        const {name, value, errFunc, onChange} = this.props
        const errors = typeof(errFunc) !== 'undefined' ? errFunc(value) : []
        onChange({name: name, value: value, errors: errors})
    }

    handleChange = (e, data) => {
        const {errFunc, onChange} = this.props
        const value = data.type === "checkbox" ? data.checked : data.value
        const errors = typeof(errFunc) !== 'undefined' ? errFunc(value) : []
        onChange({name: data.name, value: value, errors: errors})
    }
    
    render() {
        const {label, children, name, value, errors, validate, required} = this.props
        let showError = false
        if (errors && errors.length && validate) {
            showError = true
        }

        const childProps = {onChange: this.handleChange, name: name, error: showError}
        if (children.props.control && children.props.control.defaultProps && children.props.control.defaultProps.type === 'checkbox') {
            childProps['checked'] = value
        } else {
            childProps['value'] = value
        }

        return (
            <Grid.Row columns={2}>
                <Grid.Column verticalAlign='middle' width={4}>
                    <Form.Field required={required} label={label}/>
                </Grid.Column>
                <Grid.Column verticalAlign='middle' width={8}>
                    {React.cloneElement(children, childProps)}
                </Grid.Column>
                <Grid.Column verticalAlign='middle' width={4}>
                    {showError ? <Label basic pointing='left' color='red' content={assembleErrorString(errors)}/> : null}
                </Grid.Column>
            </Grid.Row>
        )

    }
}


// function FormBundle({label, children, name, value, errors, errFunc, validate, onChange, required}) {
//     let showError = false
//     if (errors && errors.length && validate) {
//         showError = true
//     }

//     // onChange({name: name, value: value, errors: errFunc(value)})

//     const handleChange = (e, data) => {
//         const errors = typeof(errFunc) !== 'undefined' ? errFunc(data.value) : []
//         onChange({name: data.name, value: data.type === "checkbox" ? data.checked : data.value, errors: errors})
//     }

//     const childProps = {onChange: handleChange, name: name, error: showError}
//     if (children.props.control && children.props.control.defaultProps && children.props.control.defaultProps.type === 'checkbox') {
//         childProps['checked'] = value
//     } else {
//         childProps['value'] = value
//     }

//     return (
//         <Grid.Row columns={2}>
//             <Grid.Column verticalAlign='middle' width={4}>
//                 <Form.Field required={required} label={label}/>
//             </Grid.Column>
//             <Grid.Column verticalAlign='middle' width={8}>
//                 {React.cloneElement(children, childProps)}
//             </Grid.Column>
//             <Grid.Column verticalAlign='middle' width={4}>
//                 {showError ? <Label basic pointing='left' color='red' content={assembleErrorString(errors)}/> : null}
//             </Grid.Column>
//         </Grid.Row>
//     )

// }

export {
    BaseForm,
    PriorsFormInput
};