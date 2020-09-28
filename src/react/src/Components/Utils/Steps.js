import React, { useContext, useReducer } from "react";
import {Step, Menu, Button, Grid, Header} from "semantic-ui-react";

const StepContext = React.createContext({})

function reducer(state, action) {
    const {activeStep, stepsCompleted, numSteps} = state
    switch (action.type) {
        case 'INCREMENT_STEP':
            const nextStep = activeStep + 1 > numSteps ? activeStep : activeStep + 1
            return {
                ...state,
                activeStep: nextStep,
                stepsCompleted: nextStep > stepsCompleted ? nextStep : stepsCompleted
            }
        case 'DECREMENT_STEP':
            const prevStep = activeStep - 1 < 0 ? activeStep : activeStep - 1
            return {
                ...state,
                activeStep: prevStep
            }
        case 'SET_STEP':
            return {
                ...state,
                activeStep: action.payload
            }
        case 'SET_VALID_FUNCTION':
            return {
                ...state,
                validFunction: {
                    ...state.validFunction,
                    ...action.payload
                }
            }
    }
}

function useStepControl(props) {
    const initialState = {
        activeStep: props.initialStep || 1,
        stepsCompleted: props.initialStep || 1,
        numSteps: props.steps.length,
        validFunction: {
            header: () => true,
            body: () => true
        }
    }
    
    const [state, dispatch] = useReducer(reducer, initialState)
    
    const nextStep = () => {
        dispatch({type: 'INCREMENT_STEP'})
    }
    
    const prevStep = () => {
        dispatch({type: 'DECREMENT_STEP'})
    }
    
    const setStep = (stepNum) => {
        dispatch({type: 'SET_STEP', payload: stepNum})
    }

    const setValidFunction = (name, fn) => {
        dispatch({type: 'SET_VALID_FUNCTION', payload: {[name]: fn}})
    }
    
    const stepList = props.steps.map((step, index) => (
        {
            key: index + 1,
            stepnum: index + 1,
            link: true,
            onClick: (e, {stepnum}) => setStep(stepnum),
            name: step.title,
            content: <Header 
                content={step.title}
                subheader={step.description}
                disabled={index + 1 > state.stepsCompleted}
                />,
            active: index + 1 === state.activeStep,
        }
    ))

    return {...state, nextStep, prevStep, setStep, stepList}
}

function StepController(props) {
    const stepProps = useStepControl(props)

    return(
        <StepContext.Provider value={stepProps}>
            {props.children(stepProps.activeStep)}
        </StepContext.Provider>
    )
}

function useStepContext() {
    const stepControlProps = useContext(StepContext)
    return stepControlProps
}

function StepButton(props) {
    const {nextStep, prevStep} = useStepContext()
    const {direction, onClick, ...buttonProps} = props

    const handleStepChange = () => {
        if (onClick) {
            if (onClick()) {
                direction === 'next' ? nextStep() : prevStep()
            }
        } else {
            direction === 'next' ? nextStep() : prevStep()
        }
    }

    return <Button type='button' onClick={handleStepChange} {...buttonProps}/>
}

function StepPage(props) {
    const {activeStep, numSteps, stepList} = useStepContext()
    return (
        <React.Fragment >
            <Grid.Row columns={2}>
                <Grid.Column width={3}>
                    <Menu as={Step.Group} pointing secondary vertical items={stepList}/>
                </Grid.Column>
                <Grid.Column width={10}>
                    {props.children}
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column children={
                    activeStep > 1 ? <StepButton onClick={props.onChangeForm} direction='back' content='Save and Back'/> : null
                } textAlign='left'/>
                <Grid.Column children={
                    activeStep < numSteps ? <StepButton onClick={props.onChangeForm} direction='next' content='Save and Continue'/> : props.submitButton
                } textAlign='right'/>
            </Grid.Row>
        </React.Fragment>
    )
}


export {StepController, StepButton, StepPage, useStepContext};