import React from "react";
import {harnessApi} from "../../index";

import { Dropdown, Header, Container } from "semantic-ui-react";
import { createFragmentContainer, commitMutation, graphql } from "react-relay";
import UpdateBilbyJob from "./mutations/UpdateBilbyJob";

class JobLabelDropdown extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            labels: this.props.data.bilbyJob.labels.map(label => {return label.name})
        }
    }
    
    handleChange = (e, {value}) => {
        this.setState({
            labels: value
        }, () => this.handleSave())
    }

    handleSave = () => {
        UpdateBilbyJob(
            {
                jobId: this.props.jobId,
                labels: this.state.labels
            },
            this.props.onUpdate
        )
    }
    
    render() {
        const allLabels = this.props.data.allLabels.map(({name, description}, index) => {
            return {
                key: name,
                text: name,
                value: name,
                content: <Header content={name} subheader={description}/>
            }
        })

        return <Dropdown onChange={this.handleChange} as={Container} options={allLabels} placeholder='Add job labels...' multiple value={this.state.labels}/>

    }
}

export default createFragmentContainer(JobLabelDropdown, {
    data: graphql`
        fragment JobLabelDropdown_data on Query @argumentDefinitions(
            jobId: {type: "ID!"}
        ) {
            bilbyJob(id: $jobId) {
                labels {
                    name
                }
            }

            allLabels {
                name
                description
            }
        }
    `
})
