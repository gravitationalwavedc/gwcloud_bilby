
import React from "react";
import {harnessApi} from "../../index";

import { Checkbox } from "semantic-ui-react";
import { createFragmentContainer, commitMutation, graphql } from "react-relay";
import UpdateBilbyJob from "./mutations/UpdateBilbyJob";

class JobPrivacyToggle extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            private: this.props.data.private,
        }
    }
    
    handleChange = (e, {checked}) => {
        this.setState({
            private: checked
        }, () => this.handleSave())
    }

    handleSave = () => {
        UpdateBilbyJob(
            {
                jobId: this.props.jobId,
                private: this.state.private,
            },
            this.props.onUpdate
        )
    }
    
    render() {
        return <Checkbox toggle label={'Private'} onChange={this.handleChange} disabled={harnessApi.currentUser.userId !== this.props.userId} checked={this.state.private}/>
    }
}

export default createFragmentContainer(JobPrivacyToggle, {
    data: graphql`
        fragment JobPrivacyToggle_data on OutputStartType{
            private
        }
    `
})




