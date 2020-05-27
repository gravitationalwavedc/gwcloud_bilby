import React from "react";
import {Grid, Table, Divider, Icon, Header} from "semantic-ui-react";
import {createFragmentContainer, graphql} from "react-relay";
import JobResultFile from "./JobResultFile";
import * as Enumerable from "linq";

class JobResults extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            order: 'last_updated',
            direction: 'ascending'
        }
    }

    handleSort = (clickedColumn) => () => {
        // This is very inelegant
        const {order, direction} = this.state
        let newState = {}
        if (order !== clickedColumn) {
            newState = {
                order: clickedColumn,
                direction: 'ascending'
            }
        } else {
            newState = {
                order: order,
                direction: direction === 'ascending' ? 'descending' : 'ascending',
            }
        }
        this.setState(newState)
    }

    render() {
        const {order, direction} = this.state;

        return <React.Fragment>
            <Grid.Column>
                {this.props.bilbyResultFiles ? (
                    <Table sortable fixed celled>
                        <Table.Header>
                            <Table.Row>
                                <Table.HeaderCell sorted={order === 'path' ? direction : null}
                                                    onClick={this.handleSort('path')}>File Path</Table.HeaderCell>
                                <Table.HeaderCell sorted={order === 'isDir' ? direction : null}
                                                    onClick={this.handleSort('isDir')}>Type</Table.HeaderCell>
                                <Table.HeaderCell sorted={order === 'fileSize' ? direction : null}
                                                    onClick={this.handleSort('fileSize')}>File Size</Table.HeaderCell>
                            </Table.Row>
                        </Table.Header>
                        <Table.Body>
                            {Enumerable.from(this.props.bilbyResultFiles.files).select((e, i) => <JobResultFile
                                key={i} bilbyResultFile={e} {...this.props}/>).toArray()}
                        </Table.Body>
                    </Table>
                ) : (
                    <h4>Job does not have any files</h4>
                )}
            </Grid.Column>
        </React.Fragment>
    }
}

export default createFragmentContainer(JobResults, {
    bilbyResultFiles: graphql`
        fragment JobResults_bilbyResultFiles on BilbyResultFiles {
            files {
                ...JobResultFile_bilbyResultFile
            }
        }
    `
});