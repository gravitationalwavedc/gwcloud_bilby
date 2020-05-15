import React from "react";
import StepForm from "../Components/Forms/StepForm";
import { graphql, createFragmentContainer } from "react-relay";
import BilbyBasePage from "./BilbyBasePage";


class BilbyJobForm extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job Form', path: '/bilby/job-form/'}
            ]
        }
        console.log(this.props)
    }
    
    render() {
        return (
            <BilbyBasePage loginRequired title='Bilby Job Form' {...this.routing}>
                <StepForm data={this.props} {...this.props}/>
            </BilbyBasePage>
        )
    }
}

export default BilbyJobForm;