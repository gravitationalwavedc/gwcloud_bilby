import React from "react";
import {Grid, Table} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../../index";
import {graphql} from "graphql";

class JobList extends React.Component {
    constructor(props) {
        super(props);
        this.rows = this.props.bilbyJobs.edges.map(({node}) => <TableRow key={node.id} name={node.name} description={node.description} lastUpdated={node.lastUpdated} actions={''}/>)
        console.log(this.rows)
    }


    render() {
        return <React.Fragment>
            <Grid.Row>
                <Grid.Column>
                    <Table>
                        <Table.Header>
                            <Table.Row>
                                <Table.HeaderCell>Name</Table.HeaderCell>
                                <Table.HeaderCell>Description</Table.HeaderCell>
                                <Table.HeaderCell>Edit Date</Table.HeaderCell>
                                <Table.HeaderCell>Actions</Table.HeaderCell>
                            </Table.Row>
                        </Table.Header>
                        <Table.Body>
                            {this.rows}
                        </Table.Body>
                    </Table>
                </Grid.Column>
            </Grid.Row>
        </React.Fragment>
    }
}

function TableRow(props) {
    const {name, description, lastUpdated, actions} = props
    return (
        <Table.Row>
            <Table.Cell content={name}/>
            <Table.Cell content={description}/>
            <Table.Cell content={lastUpdated}/>
            <Table.Cell content={actions}/>
        </Table.Row>
    )

}

export default JobList;