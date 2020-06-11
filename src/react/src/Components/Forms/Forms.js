import React from "react";
import _ from "lodash";
import {Form, Divider, Grid, Label} from "semantic-ui-react";
import {assembleErrorString} from "../../Utils/errors";


// Might need to be able to store visibility functions to calculate in handleChange

const FormContext = React.createContext()

class FormController extends React.Component {
    constructor(props) {
        super(props);

        const initialErrors = {}
        Object.keys(this.props.initialValues).map((key) => {
            initialErrors[key] = []
        })

        const initialVisible = {}
        Object.keys(this.props.initialValues).map((key) => {
            initialVisible[key] = true
        })

        this.state = {
            values: this.props.initialValues || {},
            errors: initialErrors,
            visible: initialVisible,
            touched: {},
            isValidating : false,
            isValid: false
        }
    }

    handleChange = (values, errors) => {
        this.setState(prevState => ({
            values: {
                ...prevState.values,
                ...values
            },
            errors: {
                ...prevState.errors,
                ...errors
            }
        }), () => this.setValid())
    }

    handleVisibility = (name, visible) => {
        this.setState(prevState => ({
            visible: {
                ...prevState.visible,
                [name]: visible
            }
        }))
    }

    setValid = () => {
        const notEmpty = (arr) => {return Boolean(arr && arr.length)}
        const visibleErrors = _.pick(this.state.errors, Object.keys(_.pickBy(this.state.visible, val => val)))
        
        this.setState({
            isValid: !Object.values(visibleErrors).some(notEmpty)
        })
    }

    setValidating = () => {
        this.setState({
            isValidating: true
        })
    }
        
    render() {
        return <FormContext.Provider value={{
            ...this.state,
            handleChange: this.handleChange,
            handleVisibility: this.handleVisibility,
            setValid: this.setValid,
            setInitial: this.setInitial
        }}>
            {
                this.props.children({
                    ...this.state
                })
            }
        </FormContext.Provider>
    }
}


class FormField extends React.Component {
    
    static defaultProps = {
        visible: true,
        required: true,
        valFunc: () => {},
        errFunc: () => []
    }

    componentDidMount() {
        const { name, visible } = this.props
        const { values, handleVisibility, handleChange } = this.context

        const [updatedValues, errors] = this._handleUpdatingValuesAndSettingErrors(name, values[name])

        handleVisibility(name, visible)
        handleChange(updatedValues, errors)
    }

    componentDidUpdate(prevProps) {
        const { name, visible } = this.props
        
        if (visible !== prevProps.visible) {
            this.context.handleVisibility(name, visible)
        }
    }

    handleChange = (e, data) => {
        const value = data.type === 'checkbox' ? data.checked : data.value
        const { name } = data
        
        const [values, errors] = this._handleUpdatingValuesAndSettingErrors(name, value)

        this.context.handleChange(values, errors)
    }
    
    _handleUpdatingValuesAndSettingErrors(name, value) {
        const {errFunc, linkedErrors, valFunc} = this.props

        const values = {
            [name]: value,
            ...valFunc(value)
        }

        var errors = {
            [name]: errFunc(values[name]),
            ...(_.mapValues(linkedErrors, (linkedErrFunc, linkedErrName) => linkedErrFunc(value)(this.context.values[linkedErrName])))
        }


        return [values, errors]
    }

    render() {
        const { label, name, form, required, visible } = this.props
        const value = this.context.values[name]
        const errors = this.context.errors[name]
        const { isValidating } = this.context
        
        let showError = false
        if (errors && errors.length && isValidating) {
            showError = true
        }

        const childProps = {onChange: this.handleChange, name: name, error: showError}
        if (form.props.control && form.props.control.name === 'Checkbox') {
            childProps['checked'] = value
        } else {
            childProps['value'] = value
        }

        return (
            visible ?
                <Grid.Row columns={3}>
                    <Grid.Column verticalAlign='middle' width={4}>
                        <Form.Field required={required} label={label}/>
                    </Grid.Column>
                    <Grid.Column verticalAlign='middle' width={8}>
                        {React.cloneElement(form, childProps)}
                    </Grid.Column>
                    <Grid.Column verticalAlign='middle' width={4}>
                        {showError ? <Label basic pointing='left' color='red' content={assembleErrorString(errors)}/> : null}
                    </Grid.Column>
                </Grid.Row>
            :
                null
        )

    }
}
FormField.contextType = FormContext

export {FormController, FormField, FormContext}